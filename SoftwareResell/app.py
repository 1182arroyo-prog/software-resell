from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os

PORT = int(os.environ.get("PORT", "10000"))

class Handler(BaseHTTPRequestHandler):
    def _send(self, code=200, payload=None):
        if payload is None:
            payload = {"ok": True}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # Healthchecks (Render)
    def do_HEAD(self):
        if self.path == "/" or self.path.startswith("/health"):
            self.send_response(200)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/health"):
            return self._send(200, {"ok": True, "service": "software-resell"})
        return self._send(404, {"ok": False, "error": "not_found", "path": self.path})

    def do_POST(self):
        # Aceptamos solo /webhook o /prepared
        if not (self.path.startswith("/webhook") or self.path.startswith("/prepared")):
            return self._send(404, {"ok": False, "error": "not_found", "path": self.path})

        # --- Seguridad: API KEY ---
        expected = os.environ.get("API_KEY", "")
        provided = self.headers.get("X-API-KEY", "")
        if expected and provided != expected:
            return self._send(401, {"ok": False, "error": "unauthorized"})

        # Leer body
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""

        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="ignore")}

        print("INCOMING POST", self.path, data, flush=True)

        # --- Acciones por status ---
        status = str(data.get("status", "")).upper()

        if status == "SOLD":
            print("🔥 SOLD DETECTADO - iniciando acción", flush=True)

            # Modo prueba por defecto (NO borra nada)
            modo_prueba = os.environ.get("MODO_PRUEBA", "true").lower() in ("1", "true", "yes", "y")
            if modo_prueba:
                print("🟡 MODO_PRUEBA=true → SIMULADO (no se borra nada)", flush=True)
            else:
                # Aquí conectaremos delist REAL (Depop/Posh/eBay)
                print("🔴 MODO_PRUEBA=false → delist REAL (pendiente de conectar)", flush=True)

        return self._send(200, {"ok": True, "received": data})

def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on port {PORT} ...", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
