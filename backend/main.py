from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import bcrypt

app = FastAPI()

# CORS setup for Render.com
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

# Helper functions for password hashing
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed_password.encode('utf-8'))

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

        # Hash the password and store the user
        hashed_password = hash_password(password)
        cursor.execute('INSERT INTO users (name, email, password) VALUES (?, ?, ?)',
                      (name, email, hashed_password))
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

        # Verify password
        if not verify_password(password, user[3]):  # user[3] is the hashed password
            return {"status": "error", "error": "Invalid credentials"}

        return {
            "status": "success",
            "user": {"name": user[1], "email": user[2]}  # user[1] is name, user[2] is email
        }

    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
