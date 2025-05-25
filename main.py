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

# Database setup
DATABASE = "users.db"

# List of allowed usernames (case-insensitive comparison)
ALLOWED_USERS = {"roberto", "pablo", "shafeena"}

# Initialize Argon2 password hasher
ph = PasswordHasher()

# Custom RequestValidationError handler to avoid decoding binary data
@app.exception_handler(RequestValidationError)
async def custom_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Custom handler to avoid decoding binary data in validation errors."""
    errors = []
    for error in exc.errors():
        # If the error involves binary data (e.g., profile_pic), represent it as a string
        if 'input' in error and isinstance(error['input'], bytes):
            error['input'] = "Binary data (e.g., file upload)"  # Avoid including raw bytes
        errors.append(error)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": errors},
    )

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

            # Pre-populate the database with allowed users if they don't exist
            allowed_users_data = [
                ("roberto", "roberto@example.com", hash_password("defaultpassword123"), None),
                ("pablo", "pablo@example.com", hash_password("defaultpassword123"), None),
                ("shafeena", "shafeena@example.com", hash_password("defaultpassword123"), None),
            ]

            for name, email, hashed_password, profile_pic in allowed_users_data:
                cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
                if not cursor.fetchone():
                    cursor.execute('INSERT INTO users (name, email, password, profile_pic) VALUES (?, ?, ?, ?)',
                                   (name, email, hashed_password, profile_pic))
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
    email: EmailStr = Form(...),
    password: str = Form(...),
    profile_pic: UploadFile = File(None)
):
    """Handle user signup with validation, password hashing, and profile picture upload."""
    # Normalize and validate the name
    name = name.strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name cannot be empty"
        )
    
    # Check if the name is in the allowed users list (case-insensitive)
    if name.lower() not in ALLOWED_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"User '{name}' is not allowed to sign up"
        )

    # Validate password complexity
    if len(password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters long"
        )
    if not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must contain at least one uppercase letter and one digit"
        )

    # Handle profile picture (validate before reading to avoid issues with error messages)
    profile_pic_base64: Optional[str] = None
    if profile_pic:
        # Validate file type before reading
        if not profile_pic.content_type.startswith("image/"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Profile picture must be an image file"
            )
        
        # Validate file size without reading the entire file (if possible)
        # Note: FastAPI requires reading to get the size, so we read and validate together
        try:
            contents = await profile_pic.read()
            if len(contents) > 2 * 1024 * 1024:  # Limit to 2MB
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Profile picture size must be less than 2MB"
                )
            profile_pic_base64 = base64.b64encode(contents).decode('utf-8')
        except Exception as e:
            logger.error(f"Failed to process profile picture: {str(e)}")
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
        logger.error(f"Database error during signup: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

# Login endpoint
@app.post("/login")
async def login(request: LoginRequest):
    """Handle user login with password verification."""
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
        logger.error(f"Database error during login: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {str(e)}"
        )

# Forgot Password endpoint
@app.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Handle password reset by updating the user's password in the database."""
    if len(request.new_password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be at least 8 characters long"
        )

    if not any(c.isupper() for c in request.new_password) or not any(c.isdigit() for c in request.new_password):
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
        logger.error(f"Database error during forgot-password: {str(e)}")
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
    uvicorn.run(app, host="0.0.0.0", port=10000)