from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", "10000"))
API_KEY = os.environ.get("API_KEY", "") # puede estar vacío si no quieres clave

def _json_bytes(obj):
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")

class Handler(BaseHTTPRequestHandler):
    def _send(self, code=200, payload=None):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        if payload is None:
            payload = {"ok": True}
        self.wfile.write(_json_bytes(payload))

    def _get_key_from_query(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        return (qs.get("key", [""])[0] or "").strip()

    def _authorized(self):
        # Acepta key por querystring ?key=...
        provided = self._get_key_from_query()
        if not API_KEY:
            return True # si no hay API_KEY en Render, no exige nada
        return provided == API_KEY

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # Log básico
        print(f"[GET] {path} from {self.client_address[0]}", flush=True)

        if path == "/" or path.startswith("/health"):
            return self._send(200, {"ok": True, "service": "software-resell"})
        return self._send(404, {"ok": False, "error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b""
        raw_text = raw.decode("utf-8", errors="ignore")

        # Log COMPLETO para Render Free
        print("----- INCOMING REQUEST -----", flush=True)
        print(f"Method: POST", flush=True)
        print(f"Path: {path}", flush=True)
        print(f"Query: {parsed.query}", flush=True)
        print(f"From: {self.client_address[0]}", flush=True)
        print(f"Content-Length: {length}", flush=True)
        print(f"Body(raw): {raw_text}", flush=True)
        print("----------------------------", flush=True)

        if path not in ("/webhook", "/sold", "/prepared", "/delist"):
            return self._send(404, {"ok": False, "error": "not_found"})

        if not self._authorized():
            return self._send(401, {"ok": False, "error": "unauthorized"})

        try:
            data = json.loads(raw_text) if raw_text else {}
        except Exception:
            data = {"raw": raw_text}

        # Respuesta estándar
        return self._send(200, {"ok": True, "path": path, "received": data})

def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on port {PORT} ...", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
