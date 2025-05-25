from fastapi import FastAPI, Request, Response, Form, UploadFile, File, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import base64
from typing import Optional
import logging
import os
from dotenv import load_dotenv

# Load environment variables from a .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com", "http://localhost:3000", "https://login-1-8dx3.onrender.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Custom RequestValidationError handler to avoid decoding binary data
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

# Database setup
DATABASE = "users.db"

# Load allowed users from environment variable (comma-separated list)
ALLOWED_USERS = set(os.getenv("ALLOWED_USERS", "roberto,pablo,shafeena").lower().split(","))
if not ALLOWED_USERS:
    logger.error("ALLOWED_USERS environment variable is not set or empty")
    raise ValueError("ALLOWED_USERS environment variable must be set with a comma-separated list of usernames")

# Initialize Argon2 password hasher
ph = PasswordHasher()

def init_db():
    """Initialize the SQLite database and create the users table if it doesn't exist."""
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    profile_pic TEXT  -- Store profile picture as base64 string
                )
            ''')
            conn.commit()
            logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

# Helper functions for password hashing using Argon2
def hash_password(password: str) -> str:
    """Hash a password using Argon2."""
    return ph.hash(password)

def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its Argon2 hash."""
    try:
        ph.verify(hashed_password, password)
        return True
    except VerifyMismatchError:
        return False

# Pydantic models for login and forgot password requests
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str

# Root endpoint to handle GET / requests
@app.get("/")
async def root():
    """Return a welcome message for the root path."""
    return {"message": "Welcome to the Login API. Available endpoints: /signup, /login, /forgot-password, /healthz"}

# Favicon endpoint to avoid 404 errors
@app.get("/favicon.ico")
async def favicon():
    """Return a 204 No Content response for favicon requests."""
    return Response(status_code=204)

# Signup endpoint
@app.post("/signup")
async def signup(
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    profile_pic: UploadFile = File(None)
):
    """Handle user signup with validation, password hashing, and profile picture upload."""
    logger.info(f"Received signup request for email: {email}")
    
    # Normalize and validate the name
    name = name.strip()
    if not name:
        logger.warning("Signup failed: Name cannot be empty")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name cannot be empty"
        )
    
    # Check if the name is in the allowed users list (case-insensitive)
    if name.lower() not in ALLOWED_USERS:
        logger.warning(f"Signup failed: User '{name}' is not allowed to sign up")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{name}' is not allowed to sign up"
        )

    # Manually validate email format
    email_validator = EmailStr()
    try:
        email = email_validator.validate(email)
    except ValueError:
        logger.warning(f"Signup failed: Invalid email format for email: {email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid email format"
        )

    # Validate password complexity
    if len(password) < 8:
        logger.warning(f"Signup failed: Password too short for email: {email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    if not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        logger.warning(f"Signup failed: Password complexity not met for email: {email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter and one digit"
        )

    # Handle profile picture
    profile_pic_base64: Optional[str] = None
    if profile_pic:
        try:
            # Validate file type
            if not profile_pic.content_type.startswith("image/"):
                logger.warning(f"Signup failed: Invalid profile picture type for email: {email}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Profile picture must be an image file"
                )
            
            # Read the file and convert to base64
            contents = await profile_pic.read()
            if len(contents) > 2 * 1024 * 1024:  # Limit to 2MB
                logger.warning(f"Signup failed: Profile picture too large for email: {email}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Profile picture size must be less than 2MB"
                )
            profile_pic_base64 = base64.b64encode(contents).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to process profile picture for email {email}: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to process profile picture: {str(e)}"
            )

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Check if email already exists
            cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
            if cursor.fetchone():
                logger.warning(f"Signup failed: Email already exists: {email}")
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Email already exists"
                )

            # Hash the password using Argon2
            hashed_password = hash_password(password)

            # Store the user data including the profile picture
            cursor.execute(
                'INSERT INTO users (name, email, password, profile_pic) VALUES (?, ?, ?, ?)',
                (name, email, hashed_password, profile_pic_base64)
            )
            conn.commit()
            logger.info(f"User {email} signed up successfully")

        return {
            "status": "success",
            "user": {
                "name": name,
                "email": email,
                "profilePic": profile_pic_base64
            }
        }

    except sqlite3.Error as e:
        logger.error(f"Database error during signup for email {email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

# Login endpoint
@app.post("/login")
async def login(request: LoginRequest):
    """Handle user login with password verification."""
    logger.info(f"Received login request for email: {request.email}")
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Check if user exists
            cursor.execute('SELECT * FROM users WHERE email = ?', (request.email,))
            user = cursor.fetchone()

            if not user:
                logger.warning(f"Login failed: Invalid credentials for email {request.email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )

            # Verify password
            stored_password = user[3]  # user[3] is the password field
            if not verify_password(request.password, stored_password):
                logger.warning(f"Login failed: Invalid password for email {request.email}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials"
                )

            logger.info(f"User {request.email} logged in successfully")
            return {
                "status": "success",
                "user": {"name": user[1], "email": user[2], "profilePic": user[4]}
            }

    except sqlite3.Error as e:
        logger.error(f"Database error during login for email {request.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

# Forgot Password endpoint
@app.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Handle password reset by updating the user's password in the database."""
    logger.info(f"Received forgot-password request for email: {request.email}")
    if len(request.new_password) < 8:
        logger.warning(f"Forgot-password failed: Password too short for email: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )

    if not any(c.isupper() for c in request.new_password) or not any(c.isdigit() for c in request.new_password):
        logger.warning(f"Forgot-password failed: Password complexity not met for email: {request.email}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must contain at least one uppercase letter and one digit"
        )

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()

            # Check if user exists
            cursor.execute('SELECT * FROM users WHERE email = ?', (request.email,))
            user = cursor.fetchone()
            if not user:
                logger.warning(f"Forgot password failed: User with email {request.email} does not exist")
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="User with this email does not exist"
                )

            # Hash the new password
            hashed_new_password = hash_password(request.new_password)
            # Update the user's password in the database
            cursor.execute('UPDATE users SET password = ? WHERE email = ?', (hashed_new_password, request.email))
            conn.commit()
            logger.info(f"Password reset successfully for user {request.email}")

        return {"status": "success", "message": "Password updated successfully"}

    except sqlite3.Error as e:
        logger.error(f"Database error during forgot-password for email {request.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

# Health check endpoint for Render
@app.get("/healthz")
async def health_check():
    """Return a health check status for Render."""
    return {"status": "healthy"}

# Initialize the database on startup
init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)  # Match Render port