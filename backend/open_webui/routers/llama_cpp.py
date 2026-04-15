from fastapi import APIRouter, HTTPException

from open_webui.apps.llama_cpp import (
    chat_completion,
    get_model_status,
    load_model,
    list_models,
    ChatCompletionRequest,
)

router = APIRouter(prefix="/api/v1/llama_cpp", tags=["llama-cpp"])


@router.post("/chat")
async def chat(request: ChatCompletionRequest):
    result = await chat_completion(request)
    return result


@router.get("/models")
async def models():
    return await list_models()


@router.get("/models/status")
async def models_status():
    return await get_model_status()


@router.post("/models/load")
async def models_load(model_path: str = None):
    result = await load_model(model_path)
    if not result.get("success"):
        raise HTTPException(400, detail=result.get("error"))
    return result
