from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from urllib.parse import urlparse, parse_qs
import requests
import xml.etree.ElementTree as ET

PORT = int(os.environ.get("PORT", "10000"))

# Render Environment Variables
API_KEY = os.environ.get("API_KEY", "")
EBAY_USER_TOKEN = os.environ.get("EBAY_USER_TOKEN", "")

TRADING_ENDPOINT = "https://api.ebay.com/ws/api.dll"
TRADING_COMPAT_LEVEL = "967"
TRADING_SITE_ID = "0" # 0 = US


def ebay_end_item_trading(item_id: str) -> dict:
    if not EBAY_USER_TOKEN:
        return {"ok": False, "error": "missing_EBAY_USER_TOKEN"}

    xml_body = f"""<?xml version="1.0" encoding="utf-8"?>
<EndItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{EBAY_USER_TOKEN}</eBayAuthToken>
  </RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  <EndingReason>NotAvailable</EndingReason>
</EndItemRequest>
"""

    headers = {
        "Content-Type": "text/xml",
        "X-EBAY-API-CALL-NAME": "EndItem",
        "X-EBAY-API-SITEID": TRADING_SITE_ID,
        "X-EBAY-API-COMPATIBILITY-LEVEL": TRADING_COMPAT_LEVEL,
    }

    r = requests.post(TRADING_ENDPOINT, data=xml_body.encode("utf-8"), headers=headers, timeout=25)

    result = {"http_status": r.status_code, "raw": r.text[:2000]}

    try:
        root = ET.fromstring(r.text)
        ns = {"e": "urn:ebay:apis:eBLBaseComponents"}
        result["ack"] = root.findtext("e:Ack", default="", namespaces=ns)

        err_short = root.findtext(".//e:Errors/e:ShortMessage", default="", namespaces=ns)
        err_long = root.findtext(".//e:Errors/e:LongMessage", default="", namespaces=ns)
        err_code = root.findtext(".//e:Errors/e:ErrorCode", default="", namespaces=ns)
        if err_short or err_long or err_code:
            result["error_code"] = err_code
            result["short_message"] = err_short
            result["long_message"] = err_long
    except Exception as e:
        result["parse_error"] = str(e)

    return result


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
        if not (
            self.path.startswith("/webhook")
            or self.path.startswith("/prepared")
            or self.path.startswith("/sold")
        ):
            return self._send(404, {"ok": False, "error": "not_found", "path": self.path})

        # API KEY via header or URL (?key=...)
        expected = API_KEY
        provided = self.headers.get("X-API-KEY", "")
        qs = parse_qs(urlparse(self.path).query)
        provided_qs = qs.get("key", [""])[0]

        if expected and (provided != expected) and (provided_qs != expected):
            return self._send(401, {"ok": False, "error": "unauthorized"})

        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b""

        try:
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {"raw": raw.decode("utf-8", errors="ignore")}

        print("INCOMING POST", self.path, data, flush=True)

        if self.path.startswith("/sold") or str(data.get("status", "")).upper() == "SOLD":
            ebay_item_id = str(data.get("ebay_item_id", "")).strip()
            if not ebay_item_id:
                return self._send(400, {"ok": False, "error": "missing_ebay_item_id"})

            print("🔥 SOLD RECEIVED - EndItem:", ebay_item_id, flush=True)
            ebay_result = ebay_end_item_trading(ebay_item_id)
            print("eBay EndItem result:", ebay_result, flush=True)

            return self._send(200, {"ok": True, "action": "EndItem", "ebay_result": ebay_result})

        return self._send(200, {"ok": True, "received": data, "path": self.path})


def main():
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Listening on port {PORT} ...", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
