#!/usr/bin/env python3
import os, sys, subprocess, json
from pathlib import Path

from model_bootstrap import DEFAULT_MODEL_PATH, ensure_model

ROOT = Path(__file__).resolve().parent
MODEL = str(ROOT / DEFAULT_MODEL_PATH)
PORT = "3000"

ensure_model(Path(MODEL))

env = os.environ.copy()
env["LLAMA_MODEL_PATH"] = os.path.abspath(MODEL)
env["LLAMA_CONTEXT_SIZE"] = "4096"
env["LLAMA_THREADS"] = "4"
env["WEBUI_PORT"] = PORT
env["DATA_DIR"] = str(ROOT / "data")

print(f"Model: {MODEL}")
print(f"Port: {PORT}")
print(f"Starting Open WebUI...")

subprocess.run(["./venv/bin/python", "-m", "uvicorn", "open_webui.main:app", 
    "--host", "0.0.0.0", "--port", "8080"], 
    cwd=os.path.join(os.path.dirname(__file__), "backend"), 
    env=env)
