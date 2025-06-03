from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_ollama import OllamaLLM
import io
from docx import Document
import PyPDF2
from PIL import Image
import pytesseract
import asyncio
import sqlite3
from datetime import datetime, date
import uuid
from typing import List, Dict

app = FastAPI()

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://lacd.onrender.com", "https://llama3.test-hr.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Friendly name to model name mapping
FRIENDLY_MODEL_MAP = {
    "basic": "llama3:8b",
    "ultra": "llama3:70b",
}

AVAILABLE_MODELS = list(FRIENDLY_MODEL_MAP.keys())

# In-memory store for short-term memory (session-based)
SHORT_TERM_MEMORY: Dict[str, List[Dict[str, str]]] = {}

# SQLite database setup for long-term memory
DB_PATH = "chat_history.db"

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Check if table exists and its schema
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='chat_history'")
        table_info = cursor.fetchone()
        
        # If table exists but lacks 'date' column, migrate it
        if table_info and 'date' not in table_info[0]:
            cursor.execute("ALTER TABLE chat_history RENAME TO chat_history_old")
            cursor.execute("""
                CREATE TABLE chat_history (
                    session_id TEXT,
                    timestamp TEXT,
                    date TEXT,
                    user_input TEXT,
                    model_response TEXT
                )
            """)
            cursor.execute("""
                INSERT INTO chat_history (session_id, timestamp, user_input, model_response)
                SELECT session_id, timestamp, user_input, model_response
                FROM chat_history_old
            """)
            cursor.execute("UPDATE chat_history SET date = '2025-06-03' WHERE date IS NULL")
            cursor.execute("DROP TABLE chat_history_old")
            conn.commit()
        # If table doesn't exist, create it
        elif not table_info:
            cursor.execute("""
                CREATE TABLE chat_history (
                    session_id TEXT,
                    timestamp TEXT,
                    date TEXT,
                    user_input TEXT,
                    model_response TEXT
                )
            """)
            conn.commit()

init_db()

class GenerateRequest(BaseModel):
    prompt: str
    model: str = "basic"
    max_new_tokens: int = 10000
    session_id: str | None = None  # Optional session ID for conversation tracking

def get_llm(friendly_name: str) -> OllamaLLM:
    if friendly_name not in FRIENDLY_MODEL_MAP:
        raise ValueError(f"Model '{friendly_name}' not supported. Use one of {AVAILABLE_MODELS}")
    model_name = FRIENDLY_MODEL_MAP[friendly_name]
    return OllamaLLM(model=model_name, base_url="http://127.0.0.1:11434")

def save_to_long_term_memory(session_id: str, user_input: str, model_response: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        timestamp = datetime.utcnow().isoformat()
        current_date = date.today().isoformat()
        cursor.execute(
            "INSERT INTO chat_history (session_id, timestamp, date, user_input, model_response) VALUES (?, ?, ?, ?, ?)",
            (session_id, timestamp, current_date, user_input, model_response)
        )
        conn.commit()

def get_conversation_history(session_id: str, limit: int = 5) -> List[Dict[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_input, model_response FROM chat_history WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?",
            (session_id, limit)
        )
        rows = cursor.fetchall()
        return [{"user": row[0], "assistant": row[1]} for row in rows]

def get_same_day_conversations(current_date: str, limit: int = 50) -> List[Dict[str, str]]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT session_id, user_input, model_response FROM chat_history WHERE date = ? ORDER BY timestamp DESC LIMIT ?",
            (current_date, limit)
        )
        rows = cursor.fetchall()
        return [{"session_id": row[0], "user": row[1], "assistant": row[2]} for row in rows]

def get_short_term_memory(session_id: str, limit: int = 5) -> List[Dict[str, str]]:
    return SHORT_TERM_MEMORY.get(session_id, [])[-limit:]

def update_short_term_memory(session_id: str, user_input: str, model_response: str):
    if session_id not in SHORT_TERM_MEMORY:
        SHORT_TERM_MEMORY[session_id] = []
    SHORT_TERM_MEMORY[session_id].append({"user": user_input, "assistant": model_response})
    SHORT_TERM_MEMORY[session_id] = SHORT_TERM_MEMORY[session_id][-10:]

@app.post("/generate")
async def generate_text(request: Request, file: UploadFile = File(None)):
    try:
        data = await request.json()
        prompt = data.get("prompt", "")
        friendly_name = data.get("model", "basic")
        max_new_tokens = data.get("max_new_tokens", 1000)
        session_id = data.get("session_id", str(uuid.uuid4()))  # Generate new session ID if none provided

        # Extract text from uploaded file
        if file:
            content = await file.read()
            if file.filename.endswith(".txt"):
                prompt = content.decode("utf-8")
            elif file.filename.endswith(".docx"):
                doc = Document(io.BytesIO(content))
                prompt = "\n".join([para.text for para in doc.paragraphs])
            elif file.filename.endswith(".pdf"):
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
                prompt = "\n".join([page.extract_text() or "" for page in pdf_reader.pages])
            elif file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp", ".tiff")):
                image = Image.open(io.BytesIO(content))
                prompt = pytesseract.image_to_string(image)
            else:
                return {
                    "status": "error",
                    "error": "Unsupported file type. Supported: .txt, .docx, .pdf, .png, .jpg, .jpeg, .bmp, .tiff"
                }

        if friendly_name not in AVAILABLE_MODELS:
            return {"status": "error", "error": f"Invalid model. Choose from {AVAILABLE_MODELS}"}

        # Retrieve conversation history (session-specific and same-day)
        session_history = get_short_term_memory(session_id) or get_conversation_history(session_id)
        current_date = date.today().isoformat()
        same_day_history = get_same_day_conversations(current_date)
        history_text = "\n".join(
            [f"Session {msg['session_id']}: User: {msg['user']}\nAssistant: {msg['assistant']}" for msg in same_day_history]
        ) + "\n" + "\n".join(
            [f"User: {msg['user']}\nAssistant: {msg['assistant']}" for msg in session_history]
        )

        # Construct full prompt with instruction and history
        instruction = "You are a helpful assistant. Use the following conversation history from today to provide a thoughtful, meaningful, and detailed response. History includes all sessions from today, with the current session's history prioritized:\n\n"
        full_prompt = f"{instruction}{history_text}\n\nUser: {prompt}\nAssistant:"

        llm = get_llm(friendly_name)
        response = llm.invoke(full_prompt).strip()

        # Retry if model just echoes the input
        if response == prompt.strip():
            retry_instruction = "Do not repeat the input. Analyze and respond insightfully:\n\n"
            full_prompt_retry = f"{retry_instruction}{history_text}\n\nUser: {prompt}\nAssistant:"
            response = llm.invoke(full_prompt_retry).strip()

        # Update memory stores
        update_short_term_memory(session_id, prompt, response)
        save_to_long_term_memory(session_id, prompt, response)

        return {"status": "success", "response": response, "session_id": session_id}

    except ValueError as ve:
        return {"status": "error", "error": str(ve)}
    except Exception as e:
        return {"status": "error", "error": f"Failed to generate response: {str(e)}"}

@app.get("/conversation/{session_id}")
async def get_conversation(session_id: str):
    try:
        history = get_short_term_memory(session_id) or get_conversation_history(session_id)
        if not history:
            return {"status": "error", "error": "No conversation found for this session ID"}
        return {"status": "success", "conversation": history}
    except Exception as e:
        return {"status": "error", "error": f"Failed to retrieve conversation: {str(e)}"}

@app.get("/conversations_by_date/{date_str}")
async def get_conversations_by_date(date_str: str):
    try:
        # Validate date format (YYYY-MM-DD)
        datetime.strptime(date_str, "%Y-%m-%d")
        history = get_same_day_conversations(date_str)
        if not history:
            return {"status": "error", "error": f"No conversations found for date {date_str}"}
        return {"status": "success", "conversations": history}
    except ValueError:
        return {"status": "error", "error": "Invalid date format. Use YYYY-MM-DD"}
    except Exception as e:
        return {"status": "error", "error": f"Failed to retrieve conversations: {str(e)}"}