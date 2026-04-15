#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / "models" / "Huihui-Qwopus3.5-9B-v3-abliterated-Q4_K_M.gguf"
BACKEND_PORT = os.environ.get("ASSISTANT_BACKEND_PORT", "8080")
FRONTEND_PORT = os.environ.get("ASSISTANT_FRONTEND_PORT", "4173")


def get_python() -> str:
    if os.name == "nt":
        candidate = ROOT / "venv" / "Scripts" / "pythonw.exe"
        if candidate.exists():
            return str(candidate)
        candidate = ROOT / "venv" / "Scripts" / "python.exe"
        if candidate.exists():
            return str(candidate)
    else:
        candidate = ROOT / "venv" / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    return sys.executable


def get_npm_command() -> list[str]:
    return ["npm.cmd"] if os.name == "nt" else ["npm"]


class AssistantTray:
    def __init__(self):
        self.backend_process: subprocess.Popen | None = None
        self.frontend_process: subprocess.Popen | None = None
        self.icon = pystray.Icon(
            "offline-assistant",
            self._build_icon(),
            "Offline Assistant",
            menu=pystray.Menu(
                pystray.MenuItem("Open Assistant", self.open_assistant, default=True),
                pystray.MenuItem("Start Services", self.start_services),
                pystray.MenuItem("Stop Services", self.stop_services),
                pystray.MenuItem("Restart Services", self.restart_services),
                pystray.MenuItem("Quit", self.quit_app),
            ),
        )

    def _build_icon(self) -> Image.Image:
        image = Image.new("RGBA", (64, 64), (35, 37, 44, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((8, 8, 56, 44), radius=14, fill=(88, 101, 242, 255))
        draw.ellipse((18, 20, 24, 26), fill=(255, 255, 255, 255))
        draw.ellipse((30, 20, 36, 26), fill=(255, 255, 255, 255))
        draw.ellipse((42, 20, 48, 26), fill=(255, 255, 255, 255))
        draw.polygon([(24, 44), (32, 56), (40, 44)], fill=(88, 101, 242, 255))
        return image

    def backend_url(self) -> str:
        return f"http://127.0.0.1:{BACKEND_PORT}"

    def frontend_url(self) -> str:
        if (ROOT / "build").exists():
            return self.backend_url()
        return f"http://127.0.0.1:{FRONTEND_PORT}"

    def _spawn(self, command: list[str], env: dict[str, str], cwd: Path) -> subprocess.Popen:
        kwargs = {"cwd": cwd, "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        return subprocess.Popen(command, **kwargs)

    def start_services(self, icon=None, item=None):
        threading.Thread(target=self._start_services, daemon=True).start()

    def _start_services(self):
        env = os.environ.copy()
        env["SKIP_PYODIDE_FETCH"] = "true"

        if self.backend_process is None or self.backend_process.poll() is not None:
            self.backend_process = self._spawn(
                [get_python(), "run-local.py", str(MODEL_PATH), BACKEND_PORT],
                env,
                ROOT,
            )

        if not (ROOT / "build").exists():
            if self.frontend_process is None or self.frontend_process.poll() is not None:
                npm = get_npm_command()
                self.frontend_process = self._spawn(
                    npm + ["run", "dev", "--", "--host", "127.0.0.1", "--port", FRONTEND_PORT],
                    env,
                    ROOT,
                )

        time.sleep(2)
        self.open_assistant()

    def stop_services(self, icon=None, item=None):
        for process in (self.frontend_process, self.backend_process):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()

        self.frontend_process = None
        self.backend_process = None

    def restart_services(self, icon=None, item=None):
        self.stop_services()
        self.start_services()

    def open_assistant(self, icon=None, item=None):
        webbrowser.open(self.frontend_url())

    def quit_app(self, icon=None, item=None):
        self.stop_services()
        self.icon.stop()

    def run(self):
        self.icon.run()


if __name__ == "__main__":
    AssistantTray().run()
