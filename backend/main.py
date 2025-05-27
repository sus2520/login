<<<<<<< HEAD
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import hashlib
import secrets
=======
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
>>>>>>> e841a7b (ASFGH)

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
<<<<<<< HEAD
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com", "http://localhost:3000", "https://login-1-8dx3.onrender.com"],
=======
    allow_origins=["https://lacd.onrender.com", "http://localhost:3000", "https://login-1-8dx3.onrender.com"],
>>>>>>> e841a7b (ASFGH)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

<<<<<<< HEAD
# Database setup
DATABASE = "users.db"

# List of allowed usernames (case-insensitive comparison)
ALLOWED_USERS = {"roberto", "pablo", "shafeena"}

def init_db():
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Initialize the database
init_db()

# Helper functions for password hashing using hashlib
def hash_password(password: str) -> tuple[str, str]:
    # Generate a random salt
    salt = secrets.token_hex(16)  # 16 bytes, hex-encoded
    # Combine password and salt, then hash with SHA-256
    salted_password = (password + salt).encode('utf-8')
    hashed = hashlib.sha256(salted_password).hexdigest()
    # Return the hash and salt (store both in the database)
    return hashed, salt

def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    # Recompute the hash with the provided password and stored salt
    salted_password = (password + salt).encode('utf-8')
    computed_hash = hashlib.sha256(salted_password).hexdigest()
    # Compare the computed hash with the stored hash
    return computed_hash == stored_hash

# Pydantic models for signup and login requests
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

# Signup endpoint (restricted to allowed users)
@app.post("/signup")
async def signup(request: SignupRequest):
    name = request.name
    email = request.email
    password = request.password

    # Check if the name is in the allowed users list (case-insensitive)
    if name.lower() not in ALLOWED_USERS:
        return {"status": "error", "error": f"User '{name}' is not allowed to sign up."}

    # Validate input
    if not name or not email or not password:
        return {"status": "error", "error": "Missing required fields"}

    if len(password) < 8:
        return {"status": "error", "error": "Password must be at least 8 characters long"}

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return {"status": "error", "error": "Email already exists"}

        # Hash the password and get the salt
        hashed_password, salt = hash_password(password)
        # Store the hashed password and salt (modify the table structure to store the salt)
        cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, f"{hashed_password}:{salt}"))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "user": {"name": name, "email": email}
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Login endpoint
@app.post("/login")
async def login(request: LoginRequest):
    email = request.email
    password = request.password

    # Validate input
    if not email or not password:
        return {"status": "error", "error": "Missing email or password"}

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if not user:
            return {"status": "error", "error": "Invalid credentials"}

        # Extract the stored hash and salt (stored as "hash:salt")
        stored_password = user[3]  # user[3] is the password field
        try:
            stored_hash, salt = stored_password.split(":")
        except ValueError:
            return {"status": "error", "error": "Invalid stored password format"}

        # Verify password
        if not verify_password(password, stored_hash, salt):
            return {"status": "error", "error": "Invalid credentials"}

        return {
            "status": "success",
            "user": {"name": user[1], "email": user[2]}  # user[1] is name, user[2] is email
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Add health check endpoint for Render
=======
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

>>>>>>> e841a7b (ASFGH)
@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
<<<<<<< HEAD
    uvicorn.run(app, host="0.0.0.0", port=8000)
=======
    uvicorn.run(app, host="0.0.0.0", port=10000)
>>>>>>> e841a7b (ASFGH)
