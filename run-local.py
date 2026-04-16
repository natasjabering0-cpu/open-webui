#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from model_bootstrap import DEFAULT_MODEL_PATH, ensure_model

ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / DEFAULT_MODEL_PATH


def get_python() -> str:
    venv_python = ROOT / "venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def has_nvidia_gpu() -> bool:
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
        )
        output = result.stdout.lower()
        return "rtx 4060" in output or bool(output.strip())
    except Exception:
        return False


def main() -> int:
    model = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_MODEL.resolve()
    port = sys.argv[2] if len(sys.argv) > 2 else "8080"
    model_name = os.environ.get("LLAMA_MODEL_NAME", "Legend")

    try:
        ensure_model(model, os.environ.get("LLAMA_MODEL_URL"))
    except Exception as exc:
        print(str(exc))
        return 1

    model_id = model.name
    frontend_build = ROOT / "build"
    nvidia_gpu = has_nvidia_gpu()

    env = os.environ.copy()
    env.update(
        {
            "LLAMA_MODEL_PATH": str(model),
            "LLAMA_CONTEXT_SIZE": env.get("LLAMA_CONTEXT_SIZE", "8192" if nvidia_gpu else "4096"),
            "LLAMA_THREADS": env.get("LLAMA_THREADS", "4"),
            "LLAMA_GPU_LAYERS": env.get("LLAMA_GPU_LAYERS", "-1" if nvidia_gpu else "0"),
            "LLAMA_N_BATCH": env.get("LLAMA_N_BATCH", "512"),
            "LLAMA_FLASH_ATTN": env.get("LLAMA_FLASH_ATTN", "true" if nvidia_gpu else "false"),
            "DATA_DIR": str((ROOT / "data").resolve()),
            "FRONTEND_BUILD_DIR": str(frontend_build.resolve()),
            "OFFLINE_MODE": env.get("OFFLINE_MODE", "true"),
            "ENABLE_PERSISTENT_CONFIG": "false",
            "ENABLE_OLLAMA_API": "false",
            "ENABLE_OPENAI_API": "false",
            "ENABLE_WEB_SEARCH": env.get("ENABLE_WEB_SEARCH", "true"),
            "ENABLE_IMAGE_GENERATION": "false",
            "ENABLE_CODE_EXECUTION": env.get("ENABLE_CODE_EXECUTION", "true"),
            "ENABLE_CHANNELS": "false",
            "ENABLE_NOTES": "false",
            "ENABLE_COMMUNITY_SHARING": "false",
            "DEFAULT_MODELS": model_id,
            "DEFAULT_PROMPT_SUGGESTIONS": "[]",
            "MODEL_ORDER_LIST": json.dumps([model_id]),
            "LLAMA_MODEL_NAME": model_name,
            "DEFAULT_MODEL_METADATA": json.dumps(
                {
                    "description": "Local offline single-model deployment",
                    "builtinTools": {
                        "web_search": True,
                        "code_interpreter": True,
                    },
                    "capabilities": {
                        "chat": True,
                        "vision": False,
                        "tools": True,
                        "builtin_tools": True,
                        "web_search": True,
                        "code_interpreter": True,
                    },
                }
            ),
            "DEFAULT_MODEL_PARAMS": json.dumps(
                {
                    "temperature": 0.7,
                    "top_p": 0.9,
                    "top_k": 40,
                    "repeat_penalty": 1.1,
                }
            ),
            "WEBUI_NAME": env.get("WEBUI_NAME", "Knowledgecore"),
            "HOST": env.get("HOST", "0.0.0.0"),
            "PORT": port,
        }
    )

    print(f"Starting Knowledgecore on http://localhost:{port}")
    print(f"Model: {model_name} ({model})")
    if nvidia_gpu:
        print("GPU mode: NVIDIA detected, using llama.cpp CUDA-friendly defaults")
    print(f"Frontend build: {'found' if frontend_build.exists() else 'missing (API-only until npm run build)'}")

    return subprocess.run(
        [get_python(), "-m", "uvicorn", "open_webui.main:app", "--host", env["HOST"], "--port", port],
        cwd=ROOT / "backend",
        env=env,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
