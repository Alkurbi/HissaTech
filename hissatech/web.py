"""Loopback-only assessment interface. Explicit test identities, not authentication."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
from typing import Any
from urllib.parse import unquote, urlsplit

from .domain import ROOT, ROLES, Request
from .model import DEFAULT_MODEL, LocalModel, Model
from .service import decide_proposal, get_history, get_outcome, get_request_result, inspect_proposal, submit_request
from .store import Store

ASSETS = Path(__file__).with_name("static")
MAX_BODY = 65_536


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port: int, database: Path, model: Model, model_name: str):
        self.database, self.model, self.model_name = database, model, model_name
        self.token = secrets.token_urlsafe(32)
        # Initialize/migrate once before accepting concurrent connections.
        Store(database).close()
        super().__init__(("127.0.0.1", port), DashboardHandler)


class DashboardHandler(BaseHTTPRequestHandler):
    server: DashboardServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, format: str, *args: Any) -> None:
        # Do not write prompts, payloads, or identities to HTTP access logs.
        pass

    def reply(self, status: int, data: Any, content_type: str = "application/json") -> None:
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type + "; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        self.wfile.write(body)

    def validate_browser(self, api: bool) -> None:
        port = self.server.server_address[1]
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        host = self.headers.get("Host", "")
        if host not in hosts:
            raise PermissionError("Use the dashboard's loopback address.")
        origin = self.headers.get("Origin")
        if origin is not None and origin != f"http://{host}":
            raise PermissionError("Cross-origin requests are not allowed.")
        if self.headers.get("Sec-Fetch-Site") == "cross-site":
            raise PermissionError("Cross-site requests are not allowed.")
        if api and not secrets.compare_digest(self.headers.get("X-Demo-Token", ""), self.server.token):
            raise PermissionError("Reload this local dashboard before trying again.")

    def role(self) -> str:
        role = self.headers.get("X-Demo-Role", "")
        if role not in ROLES:
            raise PermissionError("Choose a known assessment test identity.")
        return role

    def do_GET(self) -> None:
        self.dispatch(False)

    def do_POST(self) -> None:
        self.dispatch(True)

    def dispatch(self, write: bool) -> None:
        try:
            path = unquote(urlsplit(self.path).path)
            self.validate_browser(path.startswith("/api/") and path != "/api/config")
            if not write and path == "/favicon.ico":
                self.reply(204, b"", "image/x-icon")
                return
            if not write and path == "/api/config":
                self.reply(200, {"token": self.server.token, "roles": sorted(ROLES), "model": self.server.model_name})
                return
            files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"), "/app.css": ("app.css", "text/css")}
            if not write and path in files:
                name, kind = files[path]
                file = ASSETS / name
                if not file.is_file():
                    self.reply(404, {"error": "Dashboard asset is missing. Check the source installation."})
                else:
                    self.reply(200, file.read_bytes(), kind)
                return
            role = self.role()
            data: dict[str, Any] = {}
            if write:
                if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json" or self.headers.get("Transfer-Encoding"):
                    raise ValueError("Send a JSON request with a Content-Length.")
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_BODY:
                    raise ValueError("Request must be between 1 and 65536 bytes.")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("Request must be a JSON object.")
            store = Store(self.server.database)
            try:
                parts = path.strip("/").split("/")
                if not write and path == "/api/history":
                    result: Any = get_history(role, store)
                elif write and path == "/api/requests":
                    if set(data) != {"request_id", "text"}:
                        raise ValueError("Supply request_id and text only. Identity is selected outside the prompt.")
                    result = submit_request(Request(data["request_id"], role, data["text"]), store, self.server.model)
                elif not write and len(parts) == 3 and parts[:2] == ["api", "requests"]:
                    result = get_request_result(parts[2], role, store)
                elif len(parts) in {3, 4} and parts[:2] == ["api", "proposals"]:
                    if not write and len(parts) == 3:
                        result = inspect_proposal(parts[2], role, store)
                    elif not write and parts[3:] == ["outcome"]:
                        result = get_outcome(parts[2], role, store)
                    elif write and parts[3:] == ["decision"]:
                        if set(data) - {"decision", "payload_hash", "adapter_mode"} or not {"decision", "payload_hash"} <= set(data):
                            raise ValueError("Supply decision, payload_hash, and optional adapter_mode.")
                        if not all(isinstance(value, str) and value for value in data.values()):
                            raise ValueError("Decision fields must be nonempty strings.")
                        result = decide_proposal(parts[2], data["payload_hash"], role, data["decision"], store, data.get("adapter_mode", "normal"))
                    else:
                        self.reply(404, {"error": "Unknown dashboard endpoint."})
                        return
                else:
                    self.reply(404, {"error": "Unknown dashboard endpoint."})
                    return
                self.reply(200, result)
            finally:
                store.close()
        except PermissionError as error:
            self.reply(403, {"error": str(error)})
        except (ValueError, TypeError, UnicodeError) as error:
            self.reply(400, {"error": str(error)})
        except (sqlite3.Error, OSError):
            self.reply(503, {"error": "Local storage or connection is unavailable. Retry the same request ID."})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=ROOT / "dashboard.sqlite3")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()
    if args.model == "template":
        parser.error("Template responses are not available. Use an installed Ollama model.")
    if not 0 < args.port < 65536:
        parser.error("Port must be between 1 and 65535.")
    model = LocalModel(args.model)
    server = DashboardServer(args.port, args.db, model, args.model)
    print(f"HissaTech dashboard: http://127.0.0.1:{args.port}/ (trusted test identities, mock actions only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
