"""Starts the local server on 127.0.0.1 and opens the browser."""
from __future__ import annotations

import atexit
import socket
import sys
import threading
import webbrowser

import uvicorn

from .api import create_app

HOST = "127.0.0.1"  # never bind to other interfaces: firewall configs are confidential


def _free_port(start: int = 8765) -> int:
    for port in range(start, start + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found between 8765 and 8815")


def serve(port: int | None = None, open_browser: bool = True) -> None:
    port = port or _free_port()
    app = create_app()
    atexit.register(app.state.sibit.cleanup)
    url = f"http://{HOST}:{port}/"
    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning", access_log=False,
                            log_config=None if sys.stdout is None else uvicorn.config.LOGGING_CONFIG)
    server = uvicorn.Server(config)
    app.state.server = server

    if open_browser:
        def _open() -> None:
            import time

            for _ in range(100):
                if server.started:
                    webbrowser.open(url)
                    return
                time.sleep(0.05)

        threading.Thread(target=_open, daemon=True).start()
    if sys.stdout is not None:
        print("\n  Sibit — See every rule. Miss nothing.")
        print(f"  Running at {url}  (local only)")
        print("  Close this window or press Ctrl+C to quit.\n", flush=True)
    server.run()
