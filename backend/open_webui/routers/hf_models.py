from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from open_webui.apps.hf_model_catalog import (
    DeploymentBundleResponse,
    HFModelListResponse,
    SavedFilterRecord,
    TemplateSpec,
    autocomplete_models,
    build_deployment_bundle,
    delete_saved_filter,
    ensure_catalog_seeded,
    generate_template_spec,
    get_browser_html_path,
    initialize_catalog_database,
    list_favorites,
    list_models,
    list_saved_filters,
    save_filter,
    set_favorite,
    sync_hf_models,
    validate_model_for_template,
)
from open_webui.utils.auth import get_admin_user, get_verified_user

log = logging.getLogger(__name__)

router = APIRouter(prefix='/api/v1/hf-models', tags=['hf-models'])


class FavoriteForm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model_id: str
    favorite: bool = True


class ModelReferenceForm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model_id: str


class SavedFilterForm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    filters: dict[str, Any]


class TemplateSpecForm(BaseModel):
    model_config = ConfigDict(extra='forbid')

    template: Literal['simple-agent', 'RAG-agent']
    model: str
    memory: bool = False
    tools: list[str] = Field(default_factory=list)


@router.get('', response_model=HFModelListResponse)
async def get_hf_models(
    q: Optional[str] = None,
    tags: list[str] = Query(default=[]),
    formats: list[str] = Query(default=[]),
    quantizations: list[str] = Query(default=[]),
    favorites_only: bool = False,
    compatible_only: bool = False,
    sort: Literal['newest', 'best-rated', 'oldest'] = 'newest',
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_verified_user),
):
    try:
        ensure_catalog_seeded()
        return list_models(
            user_id=user.id,
            query=q,
            tags=tags,
            formats=formats,
            quantizations=quantizations,
            favorites_only=favorites_only,
            compatible_only=compatible_only,
            sort=sort,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception('Failed to query HF model catalog: %s', exc)
        raise HTTPException(status_code=502, detail='Failed to query the HF model catalog') from exc


@router.get('/autocomplete', response_model=list[str])
async def autocomplete_hf_models(
    q: str = Query(default=''),
    limit: int = Query(default=10, ge=1, le=25),
    user=Depends(get_verified_user),
):
    del user
    initialize_catalog_database()
    return autocomplete_models(q, limit=limit) if q.strip() else []


@router.post('/sync')
async def sync_catalog(
    limit: int = Query(default=200, ge=1, le=500),
    user=Depends(get_admin_user),
):
    del user
    try:
        return sync_hf_models(limit=limit)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.exception('Failed to sync Hugging Face model catalog: %s', exc)
        raise HTTPException(status_code=502, detail='Failed to refresh Hugging Face models') from exc


@router.get('/browser')
async def get_browser(user=Depends(get_verified_user)):
    del user
    try:
        return FileResponse(get_browser_html_path())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post('/validate-selection')
async def validate_selection(form_data: ModelReferenceForm, user=Depends(get_verified_user)):
    del user
    try:
        model = validate_model_for_template(form_data.model_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        'valid': True,
        'model_id': model.model_id,
        'format': model.format,
        'quantization': model.quantization,
        'llama_cpp_compatible': model.llama_cpp_compatible,
    }


@router.get('/favorites', response_model=list[str])
async def get_favorites(user=Depends(get_verified_user)):
    return list_favorites(user.id)


@router.post('/favorites')
async def update_favorite(form_data: FavoriteForm, user=Depends(get_verified_user)):
    try:
        favorite = set_favorite(user_id=user.id, model_id=form_data.model_id, favorite=form_data.favorite)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {'model_id': form_data.model_id, 'favorite': favorite}


@router.get('/saved-filters', response_model=list[SavedFilterRecord])
async def get_saved_filters(user=Depends(get_verified_user)):
    return list_saved_filters(user.id)


@router.post('/saved-filters', response_model=SavedFilterRecord)
async def create_saved_filter(form_data: SavedFilterForm, user=Depends(get_verified_user)):
    try:
        return save_filter(user.id, form_data.name, form_data.filters)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete('/saved-filters/{name}')
async def remove_saved_filter(name: str, user=Depends(get_verified_user)):
    return {'deleted': delete_saved_filter(user.id, name)}


@router.post('/template-spec', response_model=TemplateSpec)
async def create_template_spec(form_data: TemplateSpecForm, user=Depends(get_verified_user)):
    del user
    try:
        return generate_template_spec(
            template=form_data.template,
            model_id=form_data.model,
            memory=form_data.memory,
            tools=form_data.tools,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post('/deployment-bundle', response_model=DeploymentBundleResponse)
async def create_deployment_bundle(form_data: TemplateSpecForm, user=Depends(get_verified_user)):
    del user
    try:
        spec = generate_template_spec(
            template=form_data.template,
            model_id=form_data.model,
            memory=form_data.memory,
            tools=form_data.tools,
        )
        return build_deployment_bundle(spec)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
