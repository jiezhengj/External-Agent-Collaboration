#!/usr/bin/env python3
"""Cross-platform tests for the ephemeral provider response relay."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import threading
from urllib.request import Request, urlopen

from buffered_http_proxy import BufferedProviderProxy
from claude_code_adapter import ClaudeCodeAdapter, ClaudeInvocation


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


def make_launcher(root: Path) -> Path:
    source = root / "fake-claude.py"
    source.write_text(
        "import os, sys\n"
        "from urllib.request import Request, urlopen\n"
        "url = os.environ['ANTHROPIC_BASE_URL'] + '/v1/messages'\n"
        "request = Request(url, data=b'{}', headers={'Content-Type': 'application/json'}, method='POST')\n"
        "with urlopen(request, timeout=10) as response:\n"
        "    print(response.read().decode('utf-8'), flush=True)\n",
        encoding="utf-8",
    )
    if os.name == "nt":
        launcher = root / "fake-claude.cmd"
        launcher.write_text(f'@echo off\r\n"{sys.executable}" "%~dp0fake-claude.py" %*\r\n', encoding="utf-8")
        return launcher
    launcher = root / "fake-claude"
    launcher.write_text(f"#!{sys.executable}\n" + source.read_text(encoding="utf-8"), encoding="utf-8")
    launcher.chmod(0o700)
    return launcher


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

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            launcher = make_launcher(root)
            adapter = ClaudeCodeAdapter()
            code, stdout, stderr = adapter.invoke(ClaudeInvocation(
                launcher=str(launcher), prompt="test", workdir=root, config_dir=str(root),
                environment={"ANTHROPIC_BASE_URL": f"http://127.0.0.1:{upstream.server_port}/anthropic"},
                tools=[], allowed_tools=[], disallowed_tools=[], timeout=10, response_transport="buffered_sse",
            ))
            assert code == 0 and stderr == "" and "structured_output" in stdout
    finally:
        proxy.close()
        upstream.shutdown()
        upstream.server_close()
        upstream_thread.join(timeout=2)
    print("buffered-http-proxy tests passed")


if __name__ == "__main__":
    main()
