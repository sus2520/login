from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

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
            password TEXT NOT NULL
        )
    ''')

    # Pre-populate the database with allowed users if they don't exist
    allowed_users_data = [
        ("roberto", "roberto@example.com", hash_password("defaultpassword123")),
        ("pablo", "pablo@example.com", hash_password("defaultpassword123")),
        ("shafeena", "shafeena@example.com", hash_password("defaultpassword123")),
    ]

    for name, email, hashed_password in allowed_users_data:
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        if not cursor.fetchone():
            cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, hashed_password))

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

# Pydantic models for signup and login requests
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

# Root endpoint to handle GET / requests
@app.get("/")
async def root():
    """Return a welcome message for the root path."""
    return {"message": "Welcome to the Login API. Available endpoints: /signup, /login, /healthz"}

# Favicon endpoint to avoid 404 errors
@app.get("/favicon.ico")
async def favicon():
    """Return a 204 No Content response for favicon requests."""
    return Response(status_code=204)

# Signup endpoint (restricted to allowed users)
@app.post("/signup")
async def signup(request: SignupRequest):
    """Handle user signup with validation and password hashing."""
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

        # Hash the password using Argon2
        hashed_password = hash_password(password)
        # Store the hashed password (Argon2 hash includes the salt)
        cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)', (name, email, hashed_password))
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
            "user": {"name": user[1], "email": user[2]}  # user[1] is name, user[2] is email
        }

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