from fastapi import FastAPI, Request, Response, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import base64

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

def init_db():
    """Initialize the SQLite database and create the users table if it doesn't exist."""
    conn = sqlite3.connect(DATABASE)
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
    conn.close()

# Helper functions for password hashing using argon2
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
    email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str
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

# Signup endpoint (restricted to allowed users, accepts profile picture)
@app.post("/signup")
async def signup(name: str = Form(...), email: str = Form(...), password: str = Form(...), profile_pic: UploadFile = File(None)):
    """Handle user signup with validation, password hashing, and profile picture upload."""
    # Check if the name is in the allowed users list (case-insensitive)
    if name.lower() not in ALLOWED_USERS:
        return {"status": "error", "error": f"User '{name}' is not allowed to sign up."}

    # Validate input
    if not name or not email or not password:
        return {"status": "error", "error": "Missing required fields"}

    if len(password) < 8:
        return {"status": "error", "error": "Password must be at least 8 characters long"}

    # Handle profile picture
    profile_pic_base64 = None
    if profile_pic:
        try:
            # Read the file and convert to base64
            contents = await profile_pic.read()
            if len(contents) > 2 * 1024 * 1024:  # Limit to 2MB
                return {"status": "error", "error": "Profile picture size must be less than 2MB"}
            profile_pic_base64 = base64.b64encode(contents).decode('utf-8')
        except Exception as e:
            return {"status": "error", "error": f"Failed to process profile picture: {str(e)}"}

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if email already exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return {"status": "error", "error": "Email already exists"}

        # Hash the password using Argon2
        hashed_password = hash_password(password)
        # Store the user data including the profile picture
        cursor.execute('INSERT INTO users (name, email, password, profile_pic) VALUES (?, ?, ?, ?)', 
                       (name, email, hashed_password, profile_pic_base64))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "user": {"name": name, "email": email, "profilePic": profile_pic_base64}
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Login endpoint
@app.post("/login")
async def login(request: LoginRequest):
    """Handle user login with password verification."""
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

        # Verify password
        stored_password = user[3]  # user[3] is the password field
        if not verify_password(password, stored_password):
            return {"status": "error", "error": "Invalid credentials"}

        return {
            "status": "success",
            "user": {"name": user[1], "email": user[2], "profilePic": user[4]}  # Include profilePic
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Forgot Password endpoint
@app.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    """Handle password reset by updating the user's password in the database."""
    email = request.email
    new_password = request.new_password

    # Validate input
    if not email or not new_password:
        return {"status": "error", "error": "Missing email or new password"}

    if len(new_password) < 8:
        return {"status": "error", "error": "New password must be at least 8 characters long"}

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()

        # Check if user exists
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        if not user:
            conn.close()
            return {"status": "error", "error": "User with this email does not exist"}

        # Hash the new password
        hashed_new_password = hash_password(new_password)
        # Update the user's password in the database
        cursor.execute('UPDATE users SET password = ? WHERE email = ?', (hashed_new_password, email))
        conn.commit()
        conn.close()

        return {"status": "success", "message": "Password updated successfully"}

    except Exception as e:
        return {"status": "error", "error": str(e)}

# Health check endpoint for Render
@app.get("/healthz")
async def health_check():
    """Return a health check status for Render."""
    return {"status": "healthy"}

# Initialize the database on startup
init_db()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)