import os
import sys
import json
import asyncio
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Union
import llama_cpp

app = FastAPI(title="Open WebUI Minimal API")

MODEL_PATH = os.environ.get("LLAMA_MODEL_PATH", "models/Huihui-Qwopus3.5-9B-v3-abliterated-Q4_K_M.gguf")
CONTEXT_SIZE = int(os.environ.get("LLAMA_CONTEXT_SIZE", "4096"))
THREADS = int(os.environ.get("LLAMA_THREADS", "4"))

llm = None

class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "default"
    messages: List[ChatMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = 2048
    stream: bool = False

@app.on_event("startup")
async def startup():
    global llm
    print(f"Loading model: {MODEL_PATH}")
    llm = llama_cpp.Llama(
        model_path=MODEL_PATH,
        n_ctx=CONTEXT_SIZE,
        n_threads=THREADS,
        verbose=False
    )
    print("Model loaded!")

def build_prompt(messages: List[ChatMessage]) -> str:
    prompt_parts = []
    for msg in messages:
        if msg.role == "system":
            prompt_parts.append(f"System: {msg.content}")
        elif msg.role == "user":
            prompt_parts.append(f"User: {msg.content}")
        elif msg.role == "assistant":
            prompt_parts.append(f"Assistant: {msg.content}")
    prompt_parts.append("Assistant:")
    return "\n\n".join(prompt_parts) + "\n"

@app.post("/api/v1/chat")
async def chat(request: ChatRequest):
    if not llm:
        raise HTTPException(503, "Model not loaded")
    
    prompt = build_prompt(request.messages)
    
    output = llm(
        prompt,
        temperature=request.temperature,
        max_tokens=request.max_tokens or -1,
        stream=False,
        echo=False
    )
    
    response_text = output["choices"][0]["text"].strip()
    
    return {
        "model": request.model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": response_text},
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": output.get("prompt_eval_count", 0),
            "completion_tokens": output.get("eval_count", 0),
            "total_tokens": output.get("prompt_eval_count", 0) + output.get("eval_count", 0)
        }
    }

@app.get("/api/v1/models")
async def models():
    return {"models": [{"name": os.path.basename(MODEL_PATH), "path": MODEL_PATH}]}

@app.get("/health")
async def health():
    return {"status": "ok", "model_loaded": llm is not None}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)