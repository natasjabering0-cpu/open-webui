from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

DEFAULT_MODEL_PATH = Path("models/Huihui-Qwopus3.5-9B-v3-abliterated-Q4_K_M.gguf")
DEFAULT_MODEL_URL = (
    "https://huggingface.co/mradermacher/"
    "Huihui-Qwopus3.5-9B-v3-abliterated-GGUF/resolve/main/"
    "Huihui-Qwopus3.5-9B-v3-abliterated.Q4_K_M.gguf?download=1"
)
CHUNK_SIZE = 1024 * 1024


def resolve_download_url(model_path: Path, download_url: str | None = None) -> str | None:
    if download_url:
        return download_url

    if model_path.name == DEFAULT_MODEL_PATH.name:
        return os.environ.get("LLAMA_MODEL_URL", DEFAULT_MODEL_URL)

    return os.environ.get("LLAMA_MODEL_URL")


def _download_to_file(download_url: str, target_path: Path) -> None:
    part_path = target_path.with_name(f"{target_path.name}.part")
    if part_path.exists():
        part_path.unlink()

    request = Request(download_url, headers={"User-Agent": "OpenWebUI-Installer/1.0"})
    try:
        with urlopen(request, timeout=60) as response, part_path.open("wb") as handle:
            total_size = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            next_report = 0

            print(f"Downloading model to {target_path}")
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)

                if total_size:
                    percent = int(downloaded * 100 / total_size)
                    if percent >= next_report:
                        print(
                            f"\r  {percent:3d}% ({downloaded / 1024 / 1024:.1f} MB / {total_size / 1024 / 1024:.1f} MB)",
                            end="",
                            flush=True,
                        )
                        next_report = min(percent + 5, 100)
                else:
                    print(f"\r  {downloaded / 1024 / 1024:.1f} MB downloaded", end="", flush=True)

        if total_size:
            print()

        part_path.replace(target_path)
    except Exception:
        if part_path.exists():
            part_path.unlink()
        raise


def ensure_model(model_path: Path, download_url: str | None = None) -> Path:
    if model_path.exists() and model_path.stat().st_size > 0:
        return model_path

    resolved_url = resolve_download_url(model_path, download_url)
    if not resolved_url:
        raise FileNotFoundError(
            f"Model not found: {model_path}. Set LLAMA_MODEL_URL or place the file manually."
        )

    model_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _download_to_file(resolved_url, model_path)
    except URLError as exc:
        raise RuntimeError(f"Failed to download model from {resolved_url}: {exc}") from exc

    if not model_path.exists() or model_path.stat().st_size == 0:
        raise RuntimeError(f"Model download did not complete: {model_path}")

    return model_path


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    model_path = Path(args[0]) if args else DEFAULT_MODEL_PATH
    download_url = args[1] if len(args) > 1 else None
    ensure_model(model_path, download_url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
