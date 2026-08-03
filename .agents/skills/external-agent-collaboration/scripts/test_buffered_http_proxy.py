#!/usr/bin/env python3
"""Cross-platform tests for the ephemeral provider response relay."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from urllib.request import Request, urlopen

import claude_code_adapter as adapter_module
from buffered_http_proxy import BufferedProviderProxy
from claude_code_adapter import ClaudeCodeAdapter, ClaudeInvocation
from process_support import ProcessResult


VALID = {"summary": "ok", "changed_files": [], "commands_run": [], "validation_results": [], "risks": [], "uncertainty": "None."}


class UpstreamHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"
    requests: list[bytes] = []

    def log_message(self, *_args: object) -> None:
        return

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        length = int(self.headers.get("Content-Length", "0"))
        self.requests.append(self.rfile.read(length))
        body = json.dumps({"structured_output": VALID}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    upstream = ThreadingHTTPServer(("127.0.0.1", 0), UpstreamHandler)
    upstream_thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    upstream_thread.start()
    proxy = BufferedProviderProxy(f"http://127.0.0.1:{upstream.server_port}/anthropic")
    relay = proxy.start()
    try:
        request = Request(relay + "/v1/messages", data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=10) as response:
            assert response.status == 200
            assert json.loads(response.read()) == {"structured_output": VALID}
        assert UpstreamHandler.requests == [b"{}"]

        observed: dict[str, str] = {}
        original_run_bounded = adapter_module.run_bounded

        def fake_run_bounded(command: list[str], *, cwd: Path, env: dict[str, str], timeout: float | None) -> ProcessResult:
            observed["relay_url"] = env["ANTHROPIC_BASE_URL"]
            return ProcessResult(0, json.dumps({"structured_output": VALID}), "")

        adapter_module.run_bounded = fake_run_bounded
        try:
            code, stdout, stderr = ClaudeCodeAdapter().invoke(ClaudeInvocation(
                launcher="claude", prompt="test", workdir=Path.cwd(), config_dir=str(Path.cwd()),
                environment={"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{upstream.server_port}/anthropic"},
                tools=[], allowed_tools=[], disallowed_tools=[], timeout=10, response_transport="buffered_sse",
            ))
        finally:
            adapter_module.run_bounded = original_run_bounded
        assert code == 0 and stderr == "" and "structured_output" in stdout
        assert observed["relay_url"].startswith("http://127.0.0.1:")
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=2)
    print("buffered-http-proxy tests passed")


if __name__ == "__main__":
    main()
