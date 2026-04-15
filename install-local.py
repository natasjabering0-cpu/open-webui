#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LLAMA_CPP_VERSION = "0.3.20"


def run(command: list[str], cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def get_venv_python(venv_dir: Path) -> Path:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def get_npm_command() -> list[str]:
    override = os.environ.get("NPM_COMMAND")
    if override:
        return [override]

    if platform.system() == "Windows":
        local_appdata = os.environ.get("LOCALAPPDATA")
        candidates = [
            shutil.which("npm.cmd"),
            shutil.which("npm"),
            str(Path(r"C:\Program Files") / "nodejs" / "npm.cmd"),
            str(Path(local_appdata) / "Programs" / "nodejs" / "npm.cmd") if local_appdata else None,
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return [candidate]
        return ["npm.cmd"]

    return ["npm"]


def build_frontend(root: Path) -> None:
    env = os.environ.copy()
    env["SKIP_PYODIDE_FETCH"] = "true"
    npm = get_npm_command()
    run(npm + ["install"], cwd=root, env=env)
    run(npm + ["run", "build"], cwd=root, env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="Install local offline Open WebUI runtime.")
    parser.add_argument("--venv", default="venv", help="Virtualenv directory")
    parser.add_argument(
        "--llama-backend",
        choices=["cpu", "cuda"],
        default="cpu",
        help="How llama-cpp-python should be installed (cpu is safer on clean machines)",
    )
    args = parser.parse_args()

    venv_dir = (ROOT / args.venv).resolve()
    if not venv_dir.exists():
        print(f"Creating virtualenv in {venv_dir}")
        venv.create(venv_dir, with_pip=True)

    python_bin = get_venv_python(venv_dir)
    pip_env = os.environ.copy()

    run([str(python_bin), "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], cwd=ROOT, env=pip_env)
    run([str(python_bin), "-m", "pip", "install", "-r", "backend/requirements.txt"], cwd=ROOT, env=pip_env)

    if args.llama_backend == "cuda":
        cuda_env = pip_env.copy()
        cuda_env["CMAKE_ARGS"] = "-DGGML_CUDA=on"
        cuda_env["FORCE_CMAKE"] = "1"
        run(
            [
                str(python_bin),
                "-m",
                "pip",
                "install",
                "--force-reinstall",
                "--no-binary=llama-cpp-python",
                f"llama-cpp-python=={LLAMA_CPP_VERSION}",
            ],
            cwd=ROOT,
            env=cuda_env,
        )

    build_frontend(ROOT)
    (ROOT / "data").mkdir(exist_ok=True)

    print("\nInstallation complete.")
    print("Run:")
    print(f"  {python_bin} run-local.py")
    print("Or use the tray launcher:")
    print(f"  {python_bin} tray_assistant.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
