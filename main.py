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
import re

# Load .env variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://lacd.onrender.com",
        "https://llama3.test-hr.com",
        "http://localhost:3000",
        "https://login-1-8dx3.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler for validation
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.error(f"Validation error: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors()},
    )

DATABASE = "users.db"

# Allowed usernames
ALLOWED_USERS = set(os.getenv("ALLOWED_USERS", "roberto,pablo,shafeena").lower().split(","))
if not ALLOWED_USERS:
    logger.error("ALLOWED_USERS must be set")
    raise ValueError("Set ALLOWED_USERS env variable")

# Argon2 password hasher
ph = PasswordHasher()

# Email regex
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

# Initialize DB
def init_db():
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    profile_pic TEXT
                )
            ''')
            conn.commit()
            logger.info("Database initialized")
    except sqlite3.Error as e:
        logger.error(f"DB init failed: {str(e)}")
        raise

# Password helpers
def hash_password(password: str) -> str:
    return ph.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, password)
    except VerifyMismatchError:
        return False

# Pydantic models
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class ForgotPasswordRequest(BaseModel):
    email: EmailStr
    new_password: str

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
    profile_pic: UploadFile = File(None)
):
    logger.info(f"Signup request for: {email}")

    name = name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    if name.lower() not in ALLOWED_USERS:
        raise HTTPException(status_code=403, detail=f"User '{name}' is not allowed to sign up")
    if not EMAIL_REGEX.match(email):
        raise HTTPException(status_code=400, detail="Invalid email format")
    if len(password) < 8 or not any(c.isupper() for c in password) or not any(c.isdigit() for c in password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters, include an uppercase letter and a digit")

    profile_pic_base64: Optional[str] = None
    if profile_pic:
        try:
            if not profile_pic.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail="Profile picture must be an image")
            contents = await profile_pic.read()
            if len(contents) > 2 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="Profile picture size must be <2MB")
            profile_pic_base64 = base64.b64encode(contents).decode("utf-8")
        except Exception as e:
            logger.error(f"Profile pic processing failed for {email}: {e}")
            raise HTTPException(status_code=500, detail=f"Profile picture error: {e}")

    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Email already exists")
            hashed_pw = hash_password(password)
            cursor.execute(
                "INSERT INTO users (name, email, password, profile_pic) VALUES (?, ?, ?, ?)",
                (name, email, hashed_pw, profile_pic_base64)
            )
            conn.commit()
        return {
            "status": "success",
            "user": {
                "name": name,
                "email": email,
                "profilePic": profile_pic_base64
            }
        }
    except sqlite3.Error as e:
        logger.error(f"DB error during signup for {email}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/login")
async def login(request: LoginRequest):
    logger.info(f"Login request for {request.email}")
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (request.email,))
            user = cursor.fetchone()
            if not user or not verify_password(request.password, user[3]):
                raise HTTPException(status_code=401, detail="Invalid credentials")
            return {
                "status": "success",
                "user": {"name": user[1], "email": user[2], "profilePic": user[4]}
            }
    except sqlite3.Error as e:
        logger.error(f"DB error during login for {request.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    logger.info(f"Password reset request for {request.email}")
    if len(request.new_password) < 8 or not any(c.isupper() for c in request.new_password) or not any(c.isdigit() for c in request.new_password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters, include an uppercase letter and a digit")
    try:
        with sqlite3.connect(DATABASE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE email = ?", (request.email,))
            user = cursor.fetchone()
            if not user:
                raise HTTPException(status_code=404, detail="User not found")
            new_hashed = hash_password(request.new_password)
            cursor.execute("UPDATE users SET password = ? WHERE email = ?", (new_hashed, request.email))
            conn.commit()
            return {"status": "success", "message": "Password updated successfully"}
    except sqlite3.Error as e:
        logger.error(f"DB error during password reset for {request.email}: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@app.get("/healthz")
async def health_check():
    return {"status": "healthy"}

# DB init on startup
init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)
