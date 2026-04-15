#!/usr/bin/env python3
import os, sys, subprocess, json

MODEL = "models/Huihui-Qwopus3.5-9B-v3-abliterated-Q4_K_M.gguf"
PORT = "3000"

if not os.path.exists(MODEL):
    print(f"Model not found: {MODEL}")
    sys.exit(1)

env = os.environ.copy()
env["LLAMA_MODEL_PATH"] = os.path.abspath(MODEL)
env["LLAMA_CONTEXT_SIZE"] = "4096"
env["LLAMA_THREADS"] = "4"
env["WEBUI_PORT"] = PORT
env["DATA_DIR"] = "/home/larslouvre/Hentet/py-gpt-master (2)/open-webui/data"

print(f"Model: {MODEL}")
print(f"Port: {PORT}")
print(f"Starting Open WebUI...")

subprocess.run(["./venv/bin/python", "-m", "uvicorn", "open_webui.main:app", 
    "--host", "0.0.0.0", "--port", "8080"], 
    cwd=os.path.join(os.path.dirname(__file__), "backend"), 
    env=env)