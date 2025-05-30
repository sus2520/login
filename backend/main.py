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
from dotenv import load_dotenv
import re
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com"],
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

# In-memory user storage
ph = PasswordHasher()
DEFAULT_USER = {
    "name": "Shafeena",
    "email": "shafeenafarheen2025@gmail.com",
    "password": ph.hash("12345$ABCd"),
    "profile_pic": None
}
users = [DEFAULT_USER]

# Load allowed users from environment variable
ALLOWED_USERS = set(os.getenv("ALLOWED_USERS", "roberto,pablo,shafeena").lower().split(","))
if not ALLOWED_USERS:
    logger.error("ALLOWED_USERS environment variable is not set or empty")
    raise ValueError("ALLOWED_USERS environment variable must be set with a comma-separated list of usernames")

# Helper functions for password hashing
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
async def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_pic: Optional[UploadFile] = File(None)
):
    logger.info(f"Received signup request for email: {email}")

    # Normalize and validate name
    name = name.strip()
    if not name:
        logger.warning("Signup failed: Name cannot be empty")
        raise HTTPException(status_code=400, detail="Name cannot be empty")

    # Check if name is allowed
    if name.lower() not in ALLOWED_USERS:
        logger.warning(f"Signup failed: User '{name}' is not allowed to sign up")
        raise HTTPException(status_code=403, detail=f"User '{name}' is not allowed to sign up")

    # Validate email format
    if not EMAIL_REGEX.match(email):
        logger.warning(f"Signup failed: Invalid email format for email: {email}")
        raise HTTPException(status_code=400, detail="Invalid email format")

    # Validate password complexity
    if len(password) < 8:
        logger.warning(f"Signup failed: Password too short for email: {email}")
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long")
    if not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        logger.warning(f"Signup failed: Password complexity not met for email: {email}")
        raise HTTPException(status_code=400, detail="Password must contain at least one uppercase letter and one digit")

    # Check if email already exists
    if any(user["email"] == email for user in users):
        logger.warning(f"Signup failed: Email already exists: {email}")
        raise HTTPException(status_code=409, detail="Email already exists")

    # Handle profile picture
    profile_pic_base64: Optional[str] = None
    if profile_pic:
        if not profile_pic.content_type.startswith("image/"):
            logger.warning(f"Signup failed: Invalid profile picture type for email: {email}")
            raise HTTPException(status_code=400, detail="Profile picture must be an image file")
        try:
            contents = await profile_pic.read()
            if len(contents) > 2 * 1024 * 1024:  # 2MB limit
                logger.warning(f"Signup failed: Profile picture too large for email: {email}")
                raise HTTPException(status_code=400, detail="Profile picture size must be less than 2MB")
            profile_pic_base64 = base64.b64encode(contents).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to process profile picture for email {email}: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Failed to process profile picture: {str(e)}")

    # Store new user
    hashed_password = hash_password(password)
    new_user = {
        "name": name,
        "email": email,
        "password": hashed_password,
        "profile_pic": profile_pic_base64
    }
    users.append(new_user)
    logger.info(f"User {email} signed up successfully")

    return {
        "status": "success",
        "user": {"name": name, "email": email, "profilePic": profile_pic_base64}
    }

@app.post("/login")
async def login(request: LoginRequest):
    logger.info(f"Received login request for email: {request.email}")
    
    user = next((user for user in users if user["email"] == request.email), None)
    
    if not user:
        logger.warning(f"Login failed: Invalid credentials for email {request.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not verify_password(request.password, user["password"]):
        logger.warning(f"Login failed: Invalid password for email {request.email}")
        raise HTTPException(status_code=401, detail="Invalid credentials")

    logger.info(f"User {request.email} logged in successfully")
    return {
        "status": "success",
        "user": {"name": user["name"], "email": user["email"], "profilePic": user["profile_pic"]}
    }

@app.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    logger.info(f"Received forgot-password request for email: {request.email}")
    
    if len(request.new_password) < 8:
        logger.warning(f"Forgot-password failed: Password too short for email: {request.email}")
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters long")
    if not any(c.isupper() for c in request.new_password) or not any(c.isdigit() for c in request.new_password):
        logger.warning(f"Forgot-password failed: Password complexity not met for email: {request.email}")
        raise HTTPException(status_code=400, detail="New password must contain at least one uppercase letter and one digit")

    user = next((user for user in users if user["email"] == request.email), None)
    if not user:
        logger.warning(f"Forgot password failed: User with email {request.email} does not exist")
        raise HTTPException(status_code=404, detail="User with this email does not exist")

    user["password"] = hash_password(request.new_password)
    logger.info(f"Password reset successfully for user {request.email}")

    return {"status": "success", "message": "Password updated successfully"}

@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)