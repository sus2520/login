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

class GenerateRequest(BaseModel):
    prompt: str
    model: str = "basic"
    max_new_tokens: int = 10000

def get_llm(friendly_name: str) -> OllamaLLM:
    if friendly_name not in FRIENDLY_MODEL_MAP:
        raise ValueError(f"Model '{friendly_name}' not supported. Use one of {AVAILABLE_MODELS}")
    model_name = FRIENDLY_MODEL_MAP[friendly_name]
    return OllamaLLM(model=model_name, base_url="http://127.0.0.1:11434")

@app.post("/generate")
async def generate_text(request: Request, file: UploadFile = File(None)):
    try:
        data = await request.json()
        prompt = data.get("prompt", "")
        friendly_name = data.get("model", "basic")
        max_new_tokens = data.get("max_new_tokens", 1000)

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

        # Delay to simulate reading
        await asyncio.sleep(2)

        # Wrap prompt with instruction
        instruction = "Please read the following input carefully and provide a thoughtful, meaningful response detailed and elabroted response:\n\n"
        full_prompt = f"{instruction}{prompt}"

        llm = get_llm(friendly_name)
        response = llm.invoke(full_prompt).strip()

        # Retry if model just echoes the input
        if response == prompt.strip():
            retry_instruction = "Do not repeat the input. Analyze and respond insightfully:\n\n"
            full_prompt_retry = f"{retry_instruction}{prompt}"
            response = llm.invoke(full_prompt_retry).strip()

        return {"status": "success", "response": response}

    except ValueError as ve:
        return {"status": "error", "error": str(ve)}
    except Exception as e:
        return {"status": "error", "error": f"Failed to generate response: {str(e)}"}
