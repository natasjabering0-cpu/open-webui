import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from open_webui.utils.misc import (
    openai_chat_chunk_message_template,
    openai_chat_completion_message_template,
)

log = logging.getLogger(__name__)


def _get_model_id(model_path: str) -> str:
    return Path(model_path).name


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        chunks: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if text:
                    chunks.append(text)
        return "\n".join(chunks)

    return ""


def _normalize_usage(data: dict[str, Any]) -> dict[str, int]:
    prompt_tokens = int(data.get("prompt_tokens") or data.get("prompt_eval_count") or 0)
    completion_tokens = int(data.get("completion_tokens") or data.get("eval_count") or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }


class LlamaCppConfig:
    def __init__(self):
        self.model_path = os.environ.get("LLAMA_MODEL_PATH", "")
        self.model_name = os.environ.get("LLAMA_MODEL_NAME", "")
        self.context_size = int(os.environ.get("LLAMA_CONTEXT_SIZE", "4096"))
        self.threads = int(os.environ.get("LLAMA_THREADS", "4"))
        self.gpu_layers = int(os.environ.get("LLAMA_GPU_LAYERS", "0"))
        self.n_batch = int(os.environ.get("LLAMA_N_BATCH", "512"))
        self.flash_attn = os.environ.get("LLAMA_FLASH_ATTN", "false").lower() == "true"
        self.model_loaded = False
        self.current_model = self.model_name or (_get_model_id(self.model_path) if self.model_path else None)

    def is_configured(self) -> bool:
        return bool(self.model_path)

    def get_config_summary(self) -> dict[str, Any]:
        return {
            "model_path": self.model_path,
            "context_size": self.context_size,
            "threads": self.threads,
            "gpu_layers": self.gpu_layers,
            "n_batch": self.n_batch,
            "flash_attn": self.flash_attn,
            "model_loaded": self.model_loaded,
            "current_model": self.current_model,
        }


llama_cpp_config = LlamaCppConfig()


class ChatMessage(BaseModel):
    role: str
    content: Any


class ChatCompletionRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    stream: bool = False
    top_p: float = 0.9
    top_k: int = 40
    repeat_penalty: float = 1.1
    stop: Optional[str | list[str]] = None


class ChatCompletionResponse(BaseModel):
    model: str
    choices: list[dict[str, Any]]
    usage: dict[str, int]


class ModelInfo(BaseModel):
    name: str
    size: int
    modified_at: str
    path: str


class LlamaCpp:
    def __init__(self):
        self._llm = None
        self._loaded = False

    def _ensure_imported(self):
        try:
            import llama_cpp as _llama_cpp

            return _llama_cpp
        except ImportError:
            log.error("llama-cpp-python not installed. Run the local installer first.")
            raise

    def load_model(self, model_path: str, **kwargs) -> bool:
        if not os.path.exists(model_path):
            log.error("Model not found: %s", model_path)
            return False

        try:
            Llama = self._ensure_imported().Llama
            self._llm = Llama(
                model_path=model_path,
                n_ctx=kwargs.get("n_ctx", llama_cpp_config.context_size),
                n_threads=kwargs.get("n_threads", llama_cpp_config.threads),
                n_gpu_layers=kwargs.get("n_gpu_layers", llama_cpp_config.gpu_layers),
                n_batch=kwargs.get("n_batch", llama_cpp_config.n_batch),
                flash_attn=kwargs.get("flash_attn", llama_cpp_config.flash_attn),
                verbose=False,
            )
            self._loaded = True
            llama_cpp_config.model_loaded = True
            llama_cpp_config.current_model = llama_cpp_config.model_name or _get_model_id(model_path)
            log.info("Loaded llama.cpp model: %s", model_path)
            return True
        except Exception as exc:
            log.exception("Failed to load llama.cpp model: %s", exc)
            return False

    def is_loaded(self) -> bool:
        return self._loaded

    def _build_prompt(self, messages: list[ChatMessage]) -> str:
        prompt_parts = []
        for msg in messages:
            content = _extract_text_content(msg.content)
            if msg.role == "system":
                prompt_parts.append(f"System: {content}")
            elif msg.role == "user":
                prompt_parts.append(f"User: {content}")
            elif msg.role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        prompt_parts.append("Assistant:")
        return "\n\n".join(prompt_parts) + "\n"

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        stop: Optional[str | list[str]] = None,
    ) -> tuple[str, dict[str, int]]:
        if not self._loaded:
            raise RuntimeError("No llama.cpp model loaded")

        output = self._llm(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens or -1,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            stop=stop or [],
            echo=False,
            stream=False,
        )
        text = output["choices"][0]["text"].strip()
        usage = _normalize_usage(output)
        return text, usage

    async def generate_stream(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        top_p: float = 0.9,
        top_k: int = 40,
        repeat_penalty: float = 1.1,
        stop: Optional[str | list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        if not self._loaded:
            raise RuntimeError("No llama.cpp model loaded")

        for output in self._llm(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens or -1,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            stop=stop or [],
            echo=False,
            stream=True,
        ):
            text = output["choices"][0].get("text", "")
            if text:
                yield text
                await asyncio.sleep(0)

    def chat(self, messages: list[ChatMessage], **kwargs) -> ChatCompletionResponse:
        prompt = self._build_prompt(messages)
        response_text, usage = self.generate(prompt, **kwargs)

        return ChatCompletionResponse(
            model=llama_cpp_config.current_model or "llama.cpp",
            choices=[
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text,
                    },
                    "finish_reason": "stop",
                }
            ],
            usage=usage,
        )


llama_cpp = LlamaCpp()


def get_configured_model() -> Optional[dict[str, Any]]:
    model_path = llama_cpp_config.model_path
    if not model_path:
        return None

    path = Path(model_path)
    if not path.exists():
        return None

    stat = path.stat()
    model_id = _get_model_id(str(path))
    model_name = llama_cpp_config.model_name or path.stem
    return {
        "id": model_id,
        "name": model_name,
        "object": "model",
        "created": int(stat.st_mtime),
        "owned_by": "llama_cpp",
        "connection_type": "local",
        "info": {
            "meta": {
                "description": "Local offline GGUF model served through llama.cpp",
                "hidden": False,
            }
        },
        "llama_cpp": {
            "path": str(path),
            "context_size": llama_cpp_config.context_size,
            "threads": llama_cpp_config.threads,
            "gpu_layers": llama_cpp_config.gpu_layers,
            "n_batch": llama_cpp_config.n_batch,
            "flash_attn": llama_cpp_config.flash_attn,
        },
    }


async def ensure_model_loaded() -> None:
    if llama_cpp.is_loaded():
        return

    if not llama_cpp_config.is_configured():
        raise RuntimeError("LLAMA_MODEL_PATH is not configured")

    if not llama_cpp.load_model(llama_cpp_config.model_path):
        raise RuntimeError(f"Failed to load model: {llama_cpp_config.model_path}")


async def load_model(model_path: str = None) -> dict[str, Any]:
    path = model_path or llama_cpp_config.model_path
    if not path:
        return {
            "success": False,
            "error": "No model path specified. Set LLAMA_MODEL_PATH.",
        }

    success = llama_cpp.load_model(path)
    return {
        "success": success,
        "error": None if success else "Failed to load model",
    }


async def get_model_status() -> dict[str, Any]:
    return {
        "loaded": llama_cpp.is_loaded(),
        "model": llama_cpp_config.current_model,
        "config": llama_cpp_config.get_config_summary(),
    }


async def list_models() -> list[ModelInfo]:
    configured_model = get_configured_model()
    if not configured_model:
        return []

    path = Path(configured_model["llama_cpp"]["path"])
    stat = path.stat()
    return [
        ModelInfo(
            name=path.name,
            size=stat.st_size,
            modified_at=str(int(stat.st_mtime)),
            path=str(path),
        )
    ]


def _coerce_messages(messages: list[dict[str, Any]]) -> list[ChatMessage]:
    return [
        ChatMessage(
            role=message.get("role", "user"),
            content=message.get("content", ""),
        )
        for message in messages
    ]


async def generate_openai_chat_completion(form_data: dict[str, Any]):
    await ensure_model_loaded()

    messages = _coerce_messages(form_data.get("messages", []))
    prompt = llama_cpp._build_prompt(messages)
    model_name = llama_cpp_config.current_model or "llama.cpp"

    kwargs = {
        "temperature": form_data.get("temperature", 0.7),
        "max_tokens": form_data.get("max_tokens"),
        "top_p": form_data.get("top_p", 0.9),
        "top_k": form_data.get("top_k", 40),
        "repeat_penalty": form_data.get("repeat_penalty", 1.1),
        "stop": form_data.get("stop"),
    }

    if form_data.get("stream"):

        async def event_stream():
            async for chunk in llama_cpp.generate_stream(prompt, **kwargs):
                payload = openai_chat_chunk_message_template(model_name, content=chunk)
                yield f"data: {json.dumps(payload)}\n\n"

            payload = openai_chat_chunk_message_template(model_name)
            yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    response_text, usage = await asyncio.to_thread(llama_cpp.generate, prompt, **kwargs)
    return openai_chat_completion_message_template(
        model_name,
        message=response_text,
        usage=usage,
    )


async def chat_completion(request: ChatCompletionRequest) -> ChatCompletionResponse:
    await ensure_model_loaded()
    return llama_cpp.chat(
        request.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        top_k=request.top_k,
        repeat_penalty=request.repeat_penalty,
        stop=request.stop,
    )
