from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

PORT = int(os.environ.get("PORT", "10000"))

class Handler(BaseHTTPRequestHandler):
    def _send(self, code=200, payload=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is None:
            payload = {"ok": True}
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/health"):
            return self._send(200, {"ok": True, "service": "software-resell"})
        return self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        if not (self.path.startswith("/webhook") or self.path.startswith("/prepared")):
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="ignore")}
        return self._send(200, {"ok": True, "received": data})

def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on port {PORT} ...")
    server.serve_forever()

if __name__ == "__main__":
    # --- Seguridad: API KEY requerida ---
expected = os.environ.get("API_KEY", "")
provided = self.headers.get("X-API-KEY", "")

if expected and provided != expected:
    return self._send_json(401, {"ok": False, "error": "unauthorized"})
