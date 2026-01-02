import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import asyncio

from Cerebro_v2 import procesar_evento # tu cerebro ya existe

HOST = "0.0.0.0"
PORT = 5000

class Handler(BaseHTTPRequestHandler):
    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(raw) if raw else {}
        except Exception as e:
            return self._send_json(400, {"ok": False, "error": f"JSON inválido: {e}"})

        # Aceptamos /webhook o cualquier ruta
        try:
            asyncio.run(procesar_evento(data))
        except Exception as e:
            return self._send_json(500, {"ok": False, "error": str(e)})

        return self._send_json(200, {"ok": True})

    def log_message(self, format, *args):
        # Silencia logs ruidosos del servidor
        return

def main():
    print(f"🟢 Webhook server corriendo en http://localhost:{PORT}")
    print("📌 Déjalo abierto. Ahora abre otra terminal y levanta ngrok.")
    httpd = HTTPServer((HOST, PORT), Handler)
    httpd.serve_forever()

if __name__ == "__main__":
    main()__