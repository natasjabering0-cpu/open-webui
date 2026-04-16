#!/usr/bin/env python3
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import webbrowser
from urllib.error import URLError
from urllib.request import urlopen
from pathlib import Path

import pystray
from PIL import Image, ImageDraw

from model_bootstrap import DEFAULT_MODEL_PATH, ensure_model

ROOT = Path(__file__).resolve().parent
MODEL_PATH = ROOT / DEFAULT_MODEL_PATH
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
        self.backend_status = "Stopped"
        self._state_lock = threading.RLock()
        self._shutdown = threading.Event()
        self.icon = pystray.Icon(
            "knowledgecore",
            self._build_icon(),
            "Knowledgecore",
            menu=self._build_menu(),
        )
        self._status_thread = threading.Thread(target=self._monitor_backend_status, daemon=True)
        self._status_thread.start()

    def _build_menu(self) -> pystray.Menu:
        return pystray.Menu(
            pystray.MenuItem(self.backend_status_label, self._noop, enabled=False),
            pystray.MenuItem("Open Knowledgecore", self.open_assistant, default=True),
            pystray.MenuItem("Start Services", self.start_services),
            pystray.MenuItem("Stop Services", self.stop_services),
            pystray.MenuItem("Restart Services", self.restart_services),
            pystray.MenuItem("Exit", self.quit_app),
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

    def health_url(self) -> str:
        return f"{self.backend_url()}/health"

    def _spawn(self, command: list[str], env: dict[str, str], cwd: Path) -> subprocess.Popen:
        kwargs = {"cwd": cwd, "env": env}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        return subprocess.Popen(command, **kwargs)

    def backend_status_label(self, item=None) -> str:
        return f"Backend: {self.backend_status}"

    def _noop(self, icon=None, item=None):
        return None

    def refresh_menu(self) -> None:
        if hasattr(self.icon, "update_menu"):
            self.icon.update_menu()

    def _set_backend_status(self, status: str) -> None:
        if status == self.backend_status:
            return
        self.backend_status = status
        self.refresh_menu()

    def _backend_is_healthy(self) -> bool:
        try:
            with urlopen(self.health_url(), timeout=2) as response:
                return response.status == 200
        except URLError:
            return False

    def _monitor_backend_status(self) -> None:
        while not self._shutdown.is_set():
            if self.backend_status == "Downloading model":
                time.sleep(2)
                continue
            backend_alive = self.backend_process is not None and self.backend_process.poll() is None
            if self._backend_is_healthy():
                self._set_backend_status("Connected")
            elif backend_alive:
                self._set_backend_status("Starting")
            elif self.backend_process is not None:
                self._set_backend_status("Stopped")
            else:
                self._set_backend_status("Stopped")
            time.sleep(2)

    def _wait_for_backend(self, timeout_seconds: int = 30) -> bool:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline and not self._shutdown.is_set():
            if self._backend_is_healthy():
                self._set_backend_status("Connected")
                return True
            if self.backend_process is not None and self.backend_process.poll() is not None:
                self._set_backend_status("Stopped")
                return False
            time.sleep(0.5)
        return self._backend_is_healthy()

    def _start_services(self, open_browser: bool) -> None:
        env = os.environ.copy()
        env["SKIP_PYODIDE_FETCH"] = "true"

        with self._state_lock:
            if not MODEL_PATH.exists():
                self._set_backend_status("Downloading model")
            ensure_model(MODEL_PATH, env.get("LLAMA_MODEL_URL"))
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

        self._set_backend_status("Starting")
        if open_browser:
            self._wait_for_backend()
            webbrowser.open(self.frontend_url())

    def start_services(self, icon=None, item=None):
        threading.Thread(target=self._start_services, args=(False,), daemon=True).start()

    def stop_services(self, icon=None, item=None):
        with self._state_lock:
            for process in (self.frontend_process, self.backend_process):
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()

            self.frontend_process = None
            self.backend_process = None
        self._set_backend_status("Stopped")

    def restart_services(self, icon=None, item=None):
        self.stop_services()
        self.start_services()

    def open_assistant(self, icon=None, item=None):
        threading.Thread(target=self._start_services, args=(True,), daemon=True).start()

    def quit_app(self, icon=None, item=None):
        self._shutdown.set()
        self.stop_services()
        self.icon.stop()

    def run(self):
        self.icon.run()


if __name__ == "__main__":
    AssistantTray().run()
