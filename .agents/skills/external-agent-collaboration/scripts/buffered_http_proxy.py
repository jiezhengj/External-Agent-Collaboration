"""Ephemeral localhost relay for providers with incompatible SSE framing."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import secrets
import threading
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


MAX_REQUEST_BYTES = 20 * 1024 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
UPSTREAM_TIMEOUT_SECONDS = 120
FORWARDED_HEADERS = {
    "accept",
    "anthropic-beta",
    "anthropic-version",
    "authorization",
    "content-type",
    "x-api-key",
}


class BufferedProxyError(RuntimeError):
    pass


def _read_bounded(stream: Any, limit: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = stream.read(min(1024 * 1024, limit - total + 1))
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise BufferedProxyError("Provider response exceeded the bounded relay limit.")
        chunks.append(chunk)
    return b"".join(chunks)


class BufferedProviderProxy:
    """Buffer one provider HTTP response in memory and expose it on localhost.

    The relay has an unpredictable path, binds only to loopback, forwards no
    request data to logs, and is shut down by the adapter after the CLI exits.
    It exists for provider endpoints whose chunked SSE response makes the local
    Claude CLI wait after emitting its terminal event.
    """

    def __init__(self, upstream_base_url: str) -> None:
        if not isinstance(upstream_base_url, str) or not upstream_base_url.startswith(("http://", "https://")):
            raise BufferedProxyError("Buffered provider relay requires an HTTP(S) upstream base URL.")
        self.upstream_base_url = upstream_base_url.rstrip("/")
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._path_prefix: str | None = None

    def start(self) -> str:
        if self._server is not None:
            raise BufferedProxyError("Buffered provider relay is already running.")
        path_prefix = "/" + secrets.token_urlsafe(24)
        upstream_base_url = self.upstream_base_url

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.0"

            def log_message(self, *_args: object) -> None:
                return

            def _respond(self, status: int, body: bytes, content_type: str = "application/json") -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
                if not self.path.startswith(path_prefix + "/"):
                    self._respond(404, b'{"type":"error","error":{"type":"not_found"}}')
                    return
                path = self.path[len(path_prefix):]
                try:
                    content_length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._respond(400, b'{"type":"error","error":{"type":"invalid_content_length"}}')
                    return
                if content_length < 0 or content_length > MAX_REQUEST_BYTES:
                    self._respond(413, b'{"type":"error","error":{"type":"request_too_large"}}')
                    return
                body = self.rfile.read(content_length)
                headers = {
                    name: value
                    for name, value in self.headers.items()
                    if name.lower() in FORWARDED_HEADERS
                }
                request = Request(upstream_base_url + path, data=body, headers=headers, method="POST")
                try:
                    with urlopen(request, timeout=UPSTREAM_TIMEOUT_SECONDS) as response:
                        response_body = _read_bounded(response, MAX_RESPONSE_BYTES)
                        status = response.status
                        content_type = response.headers.get("Content-Type", "application/json")
                except HTTPError as error:
                    try:
                        response_body = _read_bounded(error, MAX_RESPONSE_BYTES)
                    except BufferedProxyError:
                        response_body = b'{"type":"error","error":{"type":"upstream_response_too_large"}}'
                    status = error.code
                    content_type = error.headers.get("Content-Type", "application/json")
                except (OSError, BufferedProxyError):
                    self._respond(502, b'{"type":"error","error":{"type":"upstream_unavailable"}}')
                    return
                self._respond(status, response_body, content_type)

        self._path_prefix = path_prefix
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, name="provider-buffer-relay", daemon=True)
        self._thread.start()
        return f"http://127.0.0.1:{self._server.server_port}{path_prefix}"

    def close(self) -> None:
        server, thread = self._server, self._thread
        self._server = None
        self._thread = None
        self._path_prefix = None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=2)
