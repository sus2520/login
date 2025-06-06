from fastapi import FastAPI, Request, Response, Form, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, EmailStr
import base64
from typing import Optional
import logging
import os
import json
from dotenv import load_dotenv
import re
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom RequestValidationError handler
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    def safe_encoder(obj):
        if isinstance(obj, UploadFile):
            return {"filename": obj.filename, "content_type": obj.content_type}
        elif isinstance(obj, bytes):
            return f"<{len(obj)} bytes>"
        return str(obj)
    safe_detail = jsonable_encoder(exc.errors(), custom_encoder={UploadFile: safe_encoder, bytes: safe_encoder})
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": safe_detail},
    )

# In-memory user storage with JSON persistence
ph = PasswordHasher()
DEFAULT_USERS = [
    {
        "name": "Shafeena",
        "email": "shafeenafarheen2025@gmail.com",
        "password": ph.hash("12345$ABCd"),
        "profile_pic": None
    },
    {
        "name": "Pablo",
        "email": "pablo@vya.consulting",
        "password": ph.hash("A#347.VYA#"),
        "profile_pic": None
    }
]
# In-memory user storage with JSON persistence
ph = PasswordHasher()
DEFAULT_USERS = [
    {
        "name": "Shafeena",
        "email": "shafeenafarheen2025@gmail.com",
        "password": ph.hash("12345$ABCd"),
        "profile_pic": None
    },
    {
        "name": "Pablo",
        "email": "pablo@vya.consulting",
        "password": ph.hash("A#347.VYA#"),
        "profile_pic": None
    }
]
USER_FILE = "cred.json"  # Changed from users.json to cred.json

def load_users():
    try:
        with open(USER_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.info(f"{USER_FILE} not found, initializing with DEFAULT_USERS")
        save_users(DEFAULT_USERS)  # Save default users if file doesn't exist
        return DEFAULT_USERS
    except Exception as e:
        logger.error(f"Failed to load users from {USER_FILE}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to load user data")

def save_users(users):
    try:
        with open(USER_FILE, "w") as f:
            json.dump(users, f, indent=2)
        logger.info(f"Users saved to {USER_FILE}")
    except Exception as e:
        logger.error(f"Failed to save users to {USER_FILE}: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save user data")
        
users = load_users()

# Load allowed users
ALLOWED_USERS = set(os.getenv("ALLOWED_USERS", "roberto,pablo,shafeena").lower().split(","))
if not ALLOWED_USERS:
    logger.error("ALLOWED_USERS environment variable is not set or empty")
    raise ValueError("ALLOWED_USERS environment variable must be set with a comma-separated list of usernames")

# Helper functions
def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        ph.verify(hashed_password, password)
        return True
    except VerifyMismatchError:
        return False

# Pydantic models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str

# Email regex
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Endpoints
@app.get("/")
async def root():
    return {"message": "Welcome to the Login API. Available endpoints: /signup, /login, /forgot-password, /healthz"}

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.post("/signup")
@limiter.limit("5/minute")
async def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_pic: Optional[UploadFile] = File(None)
):
    logger.info(f"Received signup request for email: {email}")
    name = name.strip()
    if not name:
        logger.warning("Signup failed: Name cannot be empty")
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if name.lower() not in ALLOWED_USERS:
        logger.warning(f"Signup failed: User '{name}' is not allowed to sign up")
        raise HTTPException(status_code=403, detail=f"User '{name}' is not allowed to sign up")
    if not EMAIL_REGEX.match(email):
        logger.warning(f"Signup failed: Invalid email format for email: {email}")
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(password) < 8:
        logger.warning(f"Signup failed: Password too short for email: {email}")
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    if not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        logger.warning(f"Signup failed: Password complexity not met for email: {email}")
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter and one digit")
    if any(user["email"] == email for user in users):
        logger.warning(f"Signup failed: Email already exists: {email}")
        raise HTTPException(status_code=409, detail="Email already exists")
    profile_pic_base64: Optional[str] = None
    if profile_pic:
        if not profile_pic.content_type.startswith("image/"):
            logger.warning(f"Signup failed: Invalid profile picture type for email: {email}")
            raise HTTPException(status_code=400, detail="Profile picture must be an image file")
        try:
            contents = await profile_pic.read()
            if len(contents) > 2 * 1024 * 1024:
                logger.warning(f"Signup failed: Profile picture too large for email: {email}")
                raise HTTPException(status_code=400, detail="Profile picture size must be less than 2MB")
            profile_pic_base64 = base64.b64encode(contents).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to process profile picture for email {email}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to process profile picture: {str(e)}")
    hashed_password = hash_password(password)
    new_user = {
        "name": name,
        "email": email,
        "password": hashed_password,
        "profile_pic": profile_pic_base64
    }
    users.append(new_user)
    save_users(users)
    logger.info(f"User {email} signed up successfully")
    return {
        "status": "success",
        "user": {"name": name, "email": email, "profilePic": profile_pic_base64}
    }

@app.post("/login")
@limiter.limit("20/minute")
async def login(request: Request, login_request: LoginRequest):
    logger.info(f"Received login request for email: {login_request.email}")
    user = next((user for user in users if user["email"] == login_request.email), None)
    if not user:
        logger.warning(f"Login failed: Invalid credentials for email {login_request.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not verify_password(login_request.password, user["password"]):
        logger.warning(f"Login failed: Invalid password for email {login_request.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")
    logger.info(f"User {login_request.email} logged in successfully")
    return {
        "status": "success",
        "user": {"name": user["name"], "email": user["email"], "profilePic": user["profile_pic"]}
    }

@app.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, forgot_request: ForgotPasswordRequest):
    logger.info(f"Received forgot-password request for email: {forgot_request.email}")
    if len(forgot_request.new_password) < 8:
        logger.warning(f"Forgot-password failed: Password too short for email: {forgot_request.email}")
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    if not any(c.isupper() for c in forgot_request.new_password) or not any(c.isdigit() for c in forgot_request.new_password):
        logger.warning(f"Forgot-password failed: Password complexity not met for email: {forgot_request.email}")
        raise HTTPException(status_code=400, detail="New password must contain at least one uppercase letter and one digit")
    user = next((user for user in users if user["email"] == forgot_request.email), None)
    if not user:
        logger.warning(f"Forgot password failed: User with email {forgot_request.email} does not exist")
        raise HTTPException(status_code=404, detail="User with this email does not exist")
    user["password"] = hash_password(forgot_request.new_password)
    save_users(users)
    logger.info(f"Password reset successfully for user {forgot_request.email}")
    response = {"status": "success", "message": "Password updated successfully"}
    logger.info(f"Response sent: {response}")
    return response

@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)