from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from gateway.service import GuardGatewayService


class GuardGatewayHandler(BaseHTTPRequestHandler):
    service: GuardGatewayService

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/audit/logs":
            self._send_json({"error": "not_found"}, status=404)
            return

        query = parse_qs(parsed.query)
        session_id = query.get("session_id", [None])[0]
        self._handle(lambda: self.service.audit_logs(session_id=session_id))

    def do_POST(self) -> None:
        routes = {
            "/expense/audit": self._expense_audit,
            "/context/build": self._context_build,
            "/attempt/start": self._attempt_start,
            "/tools/call": self._tools_call,
            "/review/output": self._review_output,
            "/policies/reload": self._policies_reload,
        }
        handler = routes.get(urlparse(self.path).path)
        if handler is None:
            self._send_json({"error": "not_found"}, status=404)
            return
        self._handle(handler)

    def _context_build(self) -> dict[str, Any]:
        body = self._read_body()
        return self.service.build_context(
            user_id=body.get("user_id", "auditor_001"),
            user_request=body["user_request"],
        )

    def _expense_audit(self) -> dict[str, Any]:
        body = self._read_body()
        return self.service.audit_expense(
            user_id=body.get("user_id", "auditor_001"),
            user_request=body["user_request"],
            expense_id=body.get("expense_id"),
            project=body.get("project", "project_a"),
        )

    def _tools_call(self) -> dict[str, Any]:
        body = self._read_body()
        return self.service.call_tool(
            session_id=body["session_id"],
            tool_name=body["tool_name"],
            arguments=body.get("arguments", {}),
        )

    def _review_output(self) -> dict[str, Any]:
        body = self._read_body()
        return self.service.review_output(
            session_id=body["session_id"],
            final_answer=body["final_answer"],
        )

    def _attempt_start(self) -> dict[str, Any]:
        body = self._read_body()
        return self.service.start_attempt(session_id=body["session_id"])

    def _policies_reload(self) -> dict[str, Any]:
        return self.service.reload_policy()

    def _handle(self, func: Any) -> None:
        try:
            self._send_json(func())
        except KeyError as exc:
            self._send_json({"error": "bad_request", "message": str(exc)}, status=400)
        except Exception as exc:  # pragma: no cover - HTTP 边界兜底
            self._send_json({"error": "internal_error", "message": str(exc)}, status=500)

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format: str, *args: Any) -> None:
        return


def run_gateway_server(host: str = "127.0.0.1", port: int = 8765) -> None:
    base_dir = Path(__file__).resolve().parent.parent
    GuardGatewayHandler.service = GuardGatewayService(base_dir=base_dir)
    server = ThreadingHTTPServer((host, port), GuardGatewayHandler)
    print(f"Guard Gateway listening on http://{host}:{port}")
    print("Endpoints: POST /context/build, POST /attempt/start, POST /tools/call, POST /review/output")
    server.serve_forever()
