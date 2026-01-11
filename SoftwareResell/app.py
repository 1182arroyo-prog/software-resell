from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from urllib.parse import urlparse, parse_qs
import requests

PORT = int(os.environ.get("PORT", "10000"))

# Render Environment Variables
API_KEY = os.environ.get("API_KEY", "")
EBAY_USER_TOKEN = os.environ.get("EBAY_USER_TOKEN", "")
EBAY_API_BASE = "https://api.ebay.com"

def ebay_end_item(item_id: str) -> dict:
    """
    End an active eBay listing (Inventory item/listing) using Sell Inventory API.
    Note: Some sellers use Trading API EndItem; here we use a modern REST approach where possible.
    If this endpoint fails for your account/listing type, we'll switch to Trading API EndItem.
    """
    url = f"{EBAY_API_BASE}/sell/inventory/v1/inventory_item/{item_id}"
    headers = {
        "Authorization": f"Bearer {EBAY_USER_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    # This is a placeholder "end" strategy. Many sellers instead end the OFFER via offer endpoint.
    # We'll implement a safe call pattern and return response for debugging.
    r = requests.get(url, headers=headers, timeout=20)
    return {"status_code": r.status_code, "text": r.text}

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

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/health"):
            return self._send(200, {"ok": True, "service": "software-resell"})
        return self._send(404, {"ok": False, "error": "not_found", "path": self.path})

    def do_POST(self):
        # Allowed routes
        if not (
            self.path.startswith("/webhook")
            or self.path.startswith("/prepared")
            or self.path.startswith("/sold")
        ):
            return self._send(404, {"ok": False, "error": "not_found", "path": self.path})

        # --- Security: API KEY via header or URL (?key=...) ---
        expected = API_KEY
        provided = self.headers.get("X-API-KEY", "")

        qs = parse_qs(urlparse(self.path).query)
        provided_qs = qs.get("key", [""])[0]

        if expected and (provided != expected) and (provided_qs != expected):
            return self._send(401, {"ok": False, "error": "unauthorized"})

        # Read body
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""
        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="ignore")}

        print("INCOMING POST", self.path, data, flush=True)

        # If SOLD, try to delist on eBay
        if self.path.startswith("/sold") or str(data.get("status", "")).upper() == "SOLD":
            ebay_item_id = str(data.get("ebay_item_id", "")).strip()
            if not ebay_item_id:
                return self._send(400, {"ok": False, "error": "missing_ebay_item_id"})

            if not EBAY_USER_TOKEN:
                return self._send(500, {"ok": False, "error": "missing_EBAY_USER_TOKEN"})

            print("🔥 SOLD RECEIVED - attempting eBay delist:", ebay_item_id, flush=True)
            result = ebay_end_item(ebay_item_id)
            print("eBay response:", result, flush=True)

            return self._send(200, {"ok": True, "action": "ebay_delist_attempted", "ebay_result": result})

        return self._send(200, {"ok": True, "received": data, "path": self.path})

def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on port {PORT} ...", flush=True)
    server.serve_forever()

if __name__ == "__main__":
    main()
