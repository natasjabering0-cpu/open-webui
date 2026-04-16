from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

import requests
from pydantic import BaseModel, ConfigDict, Field

from open_webui.env import DATA_DIR, OFFLINE_MODE, OPEN_WEBUI_DIR, STATIC_DIR

log = logging.getLogger(__name__)

HF_MODELS_API_URL = 'https://huggingface.co/api/models'
HF_MODELS_DB_PATH = DATA_DIR / 'hf_models.db'
HF_BROWSER_HTML_PATH = STATIC_DIR / 'hf-model-browser' / 'index.html'
LLAMA_CPP_TEMPLATE_DIR = OPEN_WEBUI_DIR / 'runtime_templates' / 'llama_cpp_bundle'

SUPPORTED_TEMPLATES = {'simple-agent', 'RAG-agent'}
SUPPORTED_FORMATS = {'GGUF', 'GGML'}
SUPPORTED_QUANTIZATIONS = {'4bit', '8bit'}
SUPPORTED_BROWSER_TAGS = ['RAG', 'chat', 'agent']

FORMAT_PATTERNS = {
    'GGUF': re.compile(r'(^|[\W_])gguf($|[\W_])|\.gguf$', re.IGNORECASE),
    'GGML': re.compile(r'(^|[\W_])ggml($|[\W_])|\.ggml$', re.IGNORECASE),
}
QUANTIZATION_PATTERNS = {
    '4bit': re.compile(
        r'(^|[\W_])(4bit|int4|q4|q4[_-]k|q4[_-]0|q4[_-]1|q4[_-]k[_-]m|q4[_-]k[_-]s)($|[\W_])',
        re.IGNORECASE,
    ),
    '8bit': re.compile(r'(^|[\W_])(8bit|int8|q8|q8[_-]0|q8[_-]k)($|[\W_])', re.IGNORECASE),
}


class HFModelRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    model_id: str
    format: Optional[str] = None
    quantization: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    size: Optional[str] = None
    upload_date: Optional[str] = None
    likes: int = 0
    downloads: int = 0
    huggingface_url: str
    llama_cpp_compatible: bool
    is_favorite: bool = False


class HFModelListResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    items: list[HFModelRecord]
    total: int
    sort: str = 'newest'
    available_filters: dict[str, list[str]]
    available_sorts: list[str] = Field(default_factory=lambda: ['newest', 'best-rated', 'oldest'])
    last_synced_at: Optional[str] = None


class DockerConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')

    dockerfile: str = 'Dockerfile'
    compose_file: str = 'docker-compose.yml'


class TemplateSpec(BaseModel):
    model_config = ConfigDict(extra='forbid')

    template: Literal['simple-agent', 'RAG-agent']
    model: str
    runtime: Literal['llama.cpp'] = 'llama.cpp'
    memory: bool
    tools: list[str] = Field(default_factory=list)
    docker_config: DockerConfig = Field(default_factory=DockerConfig)


class SavedFilterRecord(BaseModel):
    model_config = ConfigDict(extra='forbid')

    name: str
    filters: dict[str, Any]
    created_at: str
    updated_at: str


class DeploymentBundleResponse(BaseModel):
    model_config = ConfigDict(extra='forbid')

    spec: TemplateSpec
    dockerfile: str
    compose_file: str
    config_json: str
    resolved_model_path: Optional[str] = None
    runtime_notes: list[str] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _human_readable_size(num_bytes: int) -> str:
    units = ['B', 'KB', 'MB', 'GB', 'TB']
    value = float(num_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f'{value:.1f} {unit}' if unit != 'B' else f'{int(value)} {unit}'
        value /= 1024
    return f'{int(num_bytes)} B'


def _normalize_tags(raw_tags: Any, model_id: str, pipeline_tag: Optional[str]) -> list[str]:
    tags: list[str] = []
    if isinstance(raw_tags, list):
        for tag in raw_tags:
            if isinstance(tag, str):
                tags.append(tag.strip().lower())
    if isinstance(pipeline_tag, str) and pipeline_tag.strip():
        tags.append(pipeline_tag.strip().lower())

    searchable = ' '.join([model_id.lower(), *tags])
    if 'rag' in searchable and 'rag' not in tags:
        tags.append('rag')
    if 'chat' in searchable and 'chat' not in tags:
        tags.append('chat')
    if 'agent' in searchable and 'agent' not in tags:
        tags.append('agent')

    unique_tags = sorted({tag for tag in tags if tag})
    return ['RAG' if tag == 'rag' else tag for tag in unique_tags]


def _extract_file_names(item: dict[str, Any]) -> list[str]:
    siblings = item.get('siblings')
    if not isinstance(siblings, list):
        return []

    file_names: list[str] = []
    for sibling in siblings:
        if isinstance(sibling, dict):
            rfilename = sibling.get('rfilename')
            if isinstance(rfilename, str) and rfilename:
                file_names.append(rfilename)
    return file_names


def _detect_format(model_id: str, tags: list[str], file_names: list[str]) -> Optional[str]:
    searchable = ' '.join([model_id, *tags, *file_names])
    for fmt, pattern in FORMAT_PATTERNS.items():
        if pattern.search(searchable):
            return fmt
    return None


def _detect_quantization(model_id: str, tags: list[str], file_names: list[str]) -> Optional[str]:
    searchable = ' '.join([model_id, *tags, *file_names])
    for quantization, pattern in QUANTIZATION_PATTERNS.items():
        if pattern.search(searchable):
            return quantization
    return None


def _detect_size(item: dict[str, Any]) -> str:
    used_storage = item.get('usedStorage')
    if isinstance(used_storage, int) and used_storage > 0:
        return _human_readable_size(used_storage)

    safetensors = item.get('safetensors')
    if isinstance(safetensors, dict):
        total = safetensors.get('total')
        if isinstance(total, int) and total > 0:
            return _human_readable_size(total)

    return 'Ukendt'


def _detect_upload_date(item: dict[str, Any]) -> Optional[str]:
    for key in ('createdAt', 'lastModified'):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _to_record(item: dict[str, Any]) -> HFModelRecord:
    model_id = item.get('id')
    if not isinstance(model_id, str) or not model_id:
        raise ValueError('Missing Hugging Face model id')

    tags = _normalize_tags(item.get('tags'), model_id=model_id, pipeline_tag=item.get('pipeline_tag'))
    file_names = _extract_file_names(item)
    model_format = _detect_format(model_id, tags, file_names)
    quantization = _detect_quantization(model_id, tags, file_names)
    compatible = model_format in SUPPORTED_FORMATS

    return HFModelRecord(
        model_id=model_id,
        format=model_format,
        quantization=quantization,
        tags=tags,
        size=_detect_size(item),
        upload_date=_detect_upload_date(item),
        likes=int(item.get('likes') or 0),
        downloads=int(item.get('downloads') or 0),
        huggingface_url=f'https://huggingface.co/{model_id}',
        llama_cpp_compatible=compatible,
    )


def _validate_filter_values(
    tags: Optional[list[str]] = None,
    formats: Optional[list[str]] = None,
    quantizations: Optional[list[str]] = None,
) -> tuple[list[str], list[str], list[str]]:
    normalized_tags = [('RAG' if tag.lower() == 'rag' else tag.lower()) for tag in (tags or [])]
    normalized_formats = [fmt.upper() for fmt in (formats or [])]
    normalized_quantizations = [quant.lower() for quant in (quantizations or [])]

    invalid_formats = [fmt for fmt in normalized_formats if fmt not in SUPPORTED_FORMATS]
    invalid_quantizations = [quant for quant in normalized_quantizations if quant not in SUPPORTED_QUANTIZATIONS]
    if invalid_formats:
        raise ValueError(f'Unsupported format filters: {", ".join(invalid_formats)}')
    if invalid_quantizations:
        raise ValueError(f'Unsupported quantization filters: {", ".join(invalid_quantizations)}')

    return normalized_tags, normalized_formats, normalized_quantizations


def _parse_tags(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError('Corrupt tags payload in hf_models.db') from exc

    if not isinstance(parsed, list):
        raise ValueError('Corrupt tags payload in hf_models.db')

    result: list[str] = []
    for item in parsed:
        if isinstance(item, str) and item:
            result.append(item)
    return result


def _ensure_catalog_columns(connection: sqlite3.Connection) -> None:
    existing_columns = {
        row['name'] if isinstance(row, sqlite3.Row) else row[1]
        for row in connection.execute("PRAGMA table_info('hf_models')").fetchall()
    }
    if 'likes' not in existing_columns:
        connection.execute('ALTER TABLE hf_models ADD COLUMN likes INTEGER NOT NULL DEFAULT 0')
    if 'downloads' not in existing_columns:
        connection.execute('ALTER TABLE hf_models ADD COLUMN downloads INTEGER NOT NULL DEFAULT 0')


def _row_to_record(row: sqlite3.Row) -> HFModelRecord:
    return HFModelRecord(
        model_id=row['model_id'],
        format=row['format'],
        quantization=row['quantization'],
        tags=_parse_tags(row['tags']),
        size=row['size'],
        upload_date=row['upload_date'],
        likes=int(row['likes'] or 0),
        downloads=int(row['downloads'] or 0),
        huggingface_url=row['huggingface_url'],
        llama_cpp_compatible=bool(row['llama_cpp_compatible']),
        is_favorite=bool(row['is_favorite']),
    )


@contextmanager
def get_catalog_connection():
    initialize_catalog_database()
    connection = sqlite3.connect(HF_MODELS_DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys = ON')
    connection.execute('PRAGMA journal_mode = WAL')
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def initialize_catalog_database() -> Path:
    HF_MODELS_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(HF_MODELS_DB_PATH) as connection:
        # Keep the Hugging Face catalog isolated from the primary WebUI DB so refreshes
        # and browser metadata do not affect the main application schema.
        connection.executescript(
            '''
            CREATE TABLE IF NOT EXISTS hf_models (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                model_id TEXT NOT NULL UNIQUE,
                format TEXT,
                quantization TEXT,
                tags TEXT NOT NULL DEFAULT '[]',
                size TEXT,
                upload_date TEXT,
                likes INTEGER NOT NULL DEFAULT 0,
                downloads INTEGER NOT NULL DEFAULT 0,
                huggingface_url TEXT NOT NULL,
                llama_cpp_compatible INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS hf_model_favorites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                model_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, model_id)
            );

            CREATE TABLE IF NOT EXISTS hf_saved_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                name TEXT NOT NULL,
                filters TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, name)
            );

            CREATE TABLE IF NOT EXISTS hf_catalog_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            '''
        )
        _ensure_catalog_columns(connection)
        connection.executescript(
            '''
            CREATE INDEX IF NOT EXISTS idx_hf_models_upload_date ON hf_models(upload_date DESC);
            CREATE INDEX IF NOT EXISTS idx_hf_models_likes ON hf_models(likes DESC);
            CREATE INDEX IF NOT EXISTS idx_hf_models_format ON hf_models(format);
            CREATE INDEX IF NOT EXISTS idx_hf_models_quantization ON hf_models(quantization);
            CREATE INDEX IF NOT EXISTS idx_hf_favorites_user_model ON hf_model_favorites(user_id, model_id);
            '''
        )
    return HF_MODELS_DB_PATH


def get_last_synced_at() -> Optional[str]:
    with get_catalog_connection() as connection:
        row = connection.execute("SELECT value FROM hf_catalog_meta WHERE key = 'last_synced_at'").fetchone()
    return row['value'] if row else None


def _set_catalog_meta(connection: sqlite3.Connection, key: str, value: str) -> None:
    connection.execute(
        '''
        INSERT INTO hf_catalog_meta(key, value)
        VALUES(?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''',
        (key, value),
    )


def sync_hf_models(limit: int = 200, timeout: int = 30) -> dict[str, Any]:
    initialize_catalog_database()
    if OFFLINE_MODE:
        raise RuntimeError('Cannot refresh the Hugging Face catalog while OFFLINE_MODE is enabled.')
    if limit <= 0:
        raise ValueError('limit must be greater than zero')

    response = requests.get(
        HF_MODELS_API_URL,
        params={
            'filter': 'llama',
            'full': 'true',
            'sort': 'lastModified',
            'direction': '-1',
            'limit': limit,
        },
        headers={'Accept': 'application/json'},
        timeout=timeout,
    )
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError('Unexpected response shape from Hugging Face API')

    records = [_to_record(item) for item in payload]
    synced_at = utc_now_iso()

    with get_catalog_connection() as connection:
        connection.executemany(
            '''
            INSERT INTO hf_models (
                model_id, format, quantization, tags, size, upload_date, likes, downloads, huggingface_url, llama_cpp_compatible
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(model_id) DO UPDATE SET
                format = excluded.format,
                quantization = excluded.quantization,
                tags = excluded.tags,
                size = excluded.size,
                upload_date = excluded.upload_date,
                likes = excluded.likes,
                downloads = excluded.downloads,
                huggingface_url = excluded.huggingface_url,
                llama_cpp_compatible = excluded.llama_cpp_compatible
            ''',
            [
                (
                    record.model_id,
                    record.format,
                    record.quantization,
                    json.dumps(record.tags),
                    record.size,
                    record.upload_date,
                    record.likes,
                    record.downloads,
                    record.huggingface_url,
                    int(record.llama_cpp_compatible),
                )
                for record in records
            ],
        )
        _set_catalog_meta(connection, 'last_synced_at', synced_at)
        _set_catalog_meta(connection, 'last_sync_count', str(len(records)))

    compatible_count = sum(1 for record in records if record.llama_cpp_compatible)
    log.info(
        'Synchronized %s Hugging Face llama models into %s (%s llama.cpp-compatible)',
        len(records),
        HF_MODELS_DB_PATH,
        compatible_count,
    )
    return {
        'database': str(HF_MODELS_DB_PATH),
        'fetched': len(records),
        'compatible': compatible_count,
        'incompatible': len(records) - compatible_count,
        'last_synced_at': synced_at,
    }


def ensure_catalog_seeded(limit: int = 200) -> None:
    initialize_catalog_database()
    with get_catalog_connection() as connection:
        row = connection.execute('SELECT COUNT(*) AS count FROM hf_models').fetchone()
    if row and int(row['count']) >= min(limit, 50):
        return
    if OFFLINE_MODE:
        log.info('Skipping initial Hugging Face catalog sync because OFFLINE_MODE is enabled.')
        return
    sync_hf_models(limit=limit)


def get_model_by_id(model_id: str, user_id: Optional[str] = None) -> Optional[HFModelRecord]:
    with get_catalog_connection() as connection:
        row = connection.execute(
            '''
            SELECT
                m.*,
                CASE
                    WHEN ? IS NULL THEN 0
                    ELSE EXISTS (
                        SELECT 1
                        FROM hf_model_favorites fav
                        WHERE fav.user_id = ?
                          AND fav.model_id = m.model_id
                    )
                END AS is_favorite
            FROM hf_models m
            WHERE m.model_id = ?
            ''',
            (user_id, user_id, model_id),
        ).fetchone()

    if not row:
        return None

    return _row_to_record(row)


def list_models(
    *,
    user_id: str,
    query: Optional[str] = None,
    tags: Optional[list[str]] = None,
    formats: Optional[list[str]] = None,
    quantizations: Optional[list[str]] = None,
    favorites_only: bool = False,
    compatible_only: bool = False,
    sort: Literal['newest', 'best-rated', 'oldest'] = 'newest',
    limit: int = 50,
    offset: int = 0,
) -> HFModelListResponse:
    normalized_tags, normalized_formats, normalized_quantizations = _validate_filter_values(tags, formats, quantizations)

    where_clauses = ['1 = 1']
    where_params: list[Any] = []
    if query:
        where_clauses.append('LOWER(m.model_id) LIKE ?')
        where_params.append(f'%{query.lower()}%')
    if normalized_formats:
        placeholders = ', '.join('?' for _ in normalized_formats)
        where_clauses.append(f'UPPER(COALESCE(m.format, "")) IN ({placeholders})')
        where_params.extend(normalized_formats)
    if normalized_quantizations:
        placeholders = ', '.join('?' for _ in normalized_quantizations)
        where_clauses.append(f'LOWER(COALESCE(m.quantization, "")) IN ({placeholders})')
        where_params.extend(normalized_quantizations)
    if compatible_only:
        where_clauses.append('m.llama_cpp_compatible = 1')
    if favorites_only:
        where_clauses.append(
            '''
            EXISTS (
                SELECT 1
                FROM hf_model_favorites only_fav
                WHERE only_fav.user_id = ?
                  AND only_fav.model_id = m.model_id
            )
            '''
        )
        where_params.append(user_id)
    for tag in normalized_tags:
        where_clauses.append(
            '''
            EXISTS (
                SELECT 1
                FROM json_each(m.tags) tags_json
                WHERE LOWER(tags_json.value) = ?
            )
            '''
        )
        where_params.append(tag.lower())

    if sort == 'best-rated':
        order_by = 'COALESCE(m.likes, 0) DESC, COALESCE(m.downloads, 0) DESC, COALESCE(m.upload_date, "") DESC, LOWER(m.model_id) ASC'
    elif sort == 'oldest':
        order_by = 'COALESCE(m.upload_date, "") ASC, LOWER(m.model_id) ASC'
    else:
        order_by = 'COALESCE(m.upload_date, "") DESC, LOWER(m.model_id) ASC'
    where_sql = ' AND '.join(where_clauses)

    with get_catalog_connection() as connection:
        rows = connection.execute(
            f'''
            SELECT
                m.*,
                EXISTS (
                    SELECT 1
                    FROM hf_model_favorites fav
                    WHERE fav.user_id = ?
                      AND fav.model_id = m.model_id
                ) AS is_favorite
            FROM hf_models m
            WHERE {where_sql}
            ORDER BY {order_by}
            LIMIT ?
            OFFSET ?
            ''',
            (user_id, *where_params, limit, offset),
        ).fetchall()

        total = int(
            connection.execute(
                f'''
                SELECT COUNT(*) AS count
                FROM hf_models m
                WHERE {where_sql}
                ''',
                where_params,
            ).fetchone()['count']
        )

    items = [_row_to_record(row) for row in rows]
    return HFModelListResponse(
        items=items,
        total=total,
        sort=sort,
        available_filters={
            'tags': SUPPORTED_BROWSER_TAGS,
            'formats': sorted(SUPPORTED_FORMATS),
            'quantizations': sorted(SUPPORTED_QUANTIZATIONS),
        },
        last_synced_at=get_last_synced_at(),
    )


def autocomplete_models(query: str, limit: int = 10) -> list[str]:
    if limit <= 0:
        raise ValueError('limit must be greater than zero')
    with get_catalog_connection() as connection:
        rows = connection.execute(
            '''
            SELECT model_id
            FROM hf_models
            WHERE LOWER(model_id) LIKE ?
            ORDER BY COALESCE(upload_date, '') DESC, LOWER(model_id) ASC
            LIMIT ?
            ''',
            (f'%{query.lower()}%', limit),
        ).fetchall()
    return [str(row['model_id']) for row in rows]


def set_favorite(*, user_id: str, model_id: str, favorite: bool) -> bool:
    model = get_model_by_id(model_id, user_id=user_id)
    if not model:
        raise ValueError(f'Unknown model: {model_id}')

    with get_catalog_connection() as connection:
        if favorite:
            connection.execute(
                '''
                INSERT INTO hf_model_favorites(user_id, model_id, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id, model_id) DO NOTHING
                ''',
                (user_id, model_id, utc_now_iso()),
            )
        else:
            connection.execute(
                'DELETE FROM hf_model_favorites WHERE user_id = ? AND model_id = ?',
                (user_id, model_id),
            )
    return favorite


def list_favorites(user_id: str) -> list[str]:
    with get_catalog_connection() as connection:
        rows = connection.execute(
            '''
            SELECT model_id
            FROM hf_model_favorites
            WHERE user_id = ?
            ORDER BY created_at DESC, LOWER(model_id) ASC
            ''',
            (user_id,),
        ).fetchall()
    return [str(row['model_id']) for row in rows]


def save_filter(user_id: str, name: str, filters: dict[str, Any]) -> SavedFilterRecord:
    if not name.strip():
        raise ValueError('Saved filter name must not be empty')

    payload = json.dumps(filters, sort_keys=True)
    now = utc_now_iso()
    with get_catalog_connection() as connection:
        connection.execute(
            '''
            INSERT INTO hf_saved_filters(user_id, name, filters, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, name) DO UPDATE SET
                filters = excluded.filters,
                updated_at = excluded.updated_at
            ''',
            (user_id, name.strip(), payload, now, now),
        )

        row = connection.execute(
            '''
            SELECT name, filters, created_at, updated_at
            FROM hf_saved_filters
            WHERE user_id = ? AND name = ?
            ''',
            (user_id, name.strip()),
        ).fetchone()

    if not row:
        raise RuntimeError('Saved filter could not be read back from the catalog database')

    return SavedFilterRecord(
        name=row['name'],
        filters=json.loads(row['filters']),
        created_at=row['created_at'],
        updated_at=row['updated_at'],
    )


def list_saved_filters(user_id: str) -> list[SavedFilterRecord]:
    with get_catalog_connection() as connection:
        rows = connection.execute(
            '''
            SELECT name, filters, created_at, updated_at
            FROM hf_saved_filters
            WHERE user_id = ?
            ORDER BY updated_at DESC, name ASC
            ''',
            (user_id,),
        ).fetchall()

    return [
        SavedFilterRecord(
            name=row['name'],
            filters=json.loads(row['filters']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
        for row in rows
    ]


def delete_saved_filter(user_id: str, name: str) -> bool:
    with get_catalog_connection() as connection:
        result = connection.execute(
            'DELETE FROM hf_saved_filters WHERE user_id = ? AND name = ?',
            (user_id, name),
        )
    return result.rowcount > 0


def validate_model_for_template(model_id: str) -> HFModelRecord:
    model = get_model_by_id(model_id)
    if not model:
        raise ValueError(f'Unknown model: {model_id}')
    if not model.llama_cpp_compatible:
        raise ValueError('Selected model is not compatible with Llama.cpp')
    if model.format not in SUPPORTED_FORMATS:
        raise ValueError('Selected model format is not supported by the template generator')
    if model.quantization not in SUPPORTED_QUANTIZATIONS:
        raise ValueError('Selected model quantization must be 4bit or 8bit for deployment templates')
    return model


def generate_template_spec(
    *,
    template: Literal['simple-agent', 'RAG-agent'],
    model_id: str,
    memory: bool,
    tools: Optional[Iterable[str]] = None,
) -> TemplateSpec:
    if template not in SUPPORTED_TEMPLATES:
        raise ValueError(f'Unsupported template: {template}')

    validate_model_for_template(model_id)
    validated_tools = [tool for tool in (tools or []) if isinstance(tool, str) and tool.strip()]
    return TemplateSpec(
        template=template,
        model=model_id,
        memory=memory,
        tools=validated_tools,
    )


def _load_template_file(file_name: str) -> str:
    template_path = LLAMA_CPP_TEMPLATE_DIR / file_name
    if not template_path.exists():
        raise FileNotFoundError(f'Missing runtime template: {template_path}')
    return template_path.read_text(encoding='utf-8')


def resolve_llama_cpp_model_path(model_id: str) -> str:
    # When a repo is already present in the HF cache, llama.cpp can load directly
    # from the cached snapshot without downloading anything during deployment.
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise RuntimeError('huggingface_hub is required to resolve cached model paths') from exc

    local_files_only = True
    try:
        snapshot_path = snapshot_download(repo_id=model_id, local_files_only=local_files_only)
    except Exception as exc:
        raise FileNotFoundError(f'Cached snapshot not found for {model_id}') from exc
    snapshot_dir = Path(snapshot_path)
    if not snapshot_dir.exists():
        raise FileNotFoundError(f'Cached snapshot not found for {model_id}')

    candidates = sorted(snapshot_dir.rglob('*.gguf')) + sorted(snapshot_dir.rglob('*.ggml'))
    if not candidates:
        raise FileNotFoundError(f'No GGUF or GGML artifacts were found in the cached snapshot for {model_id}')
    return str(candidates[0])


def build_deployment_bundle(spec: TemplateSpec) -> DeploymentBundleResponse:
    validate_model_for_template(spec.model)

    dockerfile = _load_template_file('Dockerfile')
    compose_file = _load_template_file('docker-compose.yml')

    resolved_model_path: Optional[str]
    resolution_note: Optional[str] = None
    try:
        resolved_model_path = resolve_llama_cpp_model_path(spec.model)
    except FileNotFoundError:
        resolved_model_path = None
        resolution_note = (
            'No cached GGUF/GGML artifact was found locally. Populate {{MODEL_PATH}} with the resolved cache path after the model is downloaded.'
        )
    except RuntimeError as exc:
        resolved_model_path = None
        resolution_note = f'Cached path resolution is unavailable in this environment: {exc}'

    config_payload = {
        **spec.model_dump(),
        'model_path': '{{MODEL_PATH}}',
        'memory_flag': '{{MEMORY_FLAG}}',
    }

    runtime_notes = [
        'Docker templates intentionally keep {{MODEL_PATH}} and {{MEMORY_FLAG}} as placeholders for reproducible bundles.',
        'If the Hugging Face snapshot is already cached locally, llama.cpp can load the selected GGUF/GGML artifact directly from the resolved path.',
    ]
    if resolved_model_path:
        runtime_notes.append(f'Cached artifact detected for llama.cpp: {resolved_model_path}')
    elif resolution_note:
        runtime_notes.append(resolution_note)

    return DeploymentBundleResponse(
        spec=spec,
        dockerfile=dockerfile,
        compose_file=compose_file,
        config_json=json.dumps(config_payload, indent=2),
        resolved_model_path=resolved_model_path,
        runtime_notes=runtime_notes,
    )


def get_browser_html_path() -> Path:
    if not HF_BROWSER_HTML_PATH.exists():
        raise FileNotFoundError(f'Missing HF model browser UI: {HF_BROWSER_HTML_PATH}')
    return HF_BROWSER_HTML_PATH


initialize_catalog_database()
