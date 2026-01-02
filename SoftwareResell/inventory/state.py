import json
from pathlib import Path

STATE_FILE = Path("inventory/state.json")

def _load_state():
    if not STATE_FILE.exists():
        return {}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def _save_state(data):
    STATE_FILE.parent.mkdir(exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def marcar_vendido(sku: str, plataforma: str):
    data = _load_state()

    if sku not in data:
        data[sku] = {
            "status": "SOLD",
            "sold_on": plataforma,
            "platforms": {
                "ebay": False,
                "depop": False,
                "poshmark": False
            }
        }

    data[sku]["status"] = "SOLD"
    data[sku]["sold_on"] = plataforma

    _save_state(data)