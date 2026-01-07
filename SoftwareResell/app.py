from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

PORT = int(os.environ.get("PORT", "10000"))

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code=200, payload=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is None:
            payload = {"ok": True}
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def _require_api_key(self):
        expected = os.environ.get("API_KEY", "")
        if not expected:
            return True # no security enabled
        provided = self.headers.get("X-API-KEY", "")
        if provided != expected:
            self._send_json(401, {"ok": False, "error": "unauthorized"})
            return False
        return True

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/health"):
            return self._send_json(200, {"ok": True, "service": "software-resell"})
        return self._send_json(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        # Allow these endpoints:
        allowed = ("/webhook", "/prepared", "/sold")
        if not any(self.path.startswith(p) for p in allowed):
            return self._send_json(404, {"ok": False, "error": "not_found"})

        # API KEY check (if enabled)
        if not self._require_api_key():
            return

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""

        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="ignore")}

        print(f"INCOMING {self.command} {self.path} -> {data}")

        return self._send_json(200, {"ok": True, "path": self.path, "received": data})

def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on port {PORT} ...")
    server.serve_forever()

if __name__ == "__main__":
    main()
