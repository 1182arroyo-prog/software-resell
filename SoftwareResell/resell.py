import json
import re
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

import requests
import yaml

# =========================
# CONFIG / PATHS
# =========================
ROOT = Path(__file__).resolve().parent
DRAFTS_DIR = ROOT / "drafts"
LOGS_DIR = ROOT / "logs"
STATE_PATH = ROOT / "inventory" / "state.json"
EBAY_YAML = ROOT / "ebay.yaml"

DRAFTS_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)
STATE_PATH.parent.mkdir(exist_ok=True)

ACCIONES_LOG = LOGS_DIR / "acciones.log"
CROSSLIST_LOG = LOGS_DIR / "crosslist.log"
MAP_PATH = ROOT / "inventory" / "map.json" # item_id -> platform ids (posh/depop), etc.

# Cambia a False cuando ya estés listo en producción
MODO_PRUEBA = True

# =========================
# UTIL
# =========================
def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def log_line(path: Path, msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.parent.mkdir(exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{ts} | {msg}\n")

def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_html(html: str) -> str:
    # Quita tags y entidades simples
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    # Normaliza
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text

def one_line(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()

def extract_item_id(value: str) -> str:
    s = value.strip()

    # Si ya es puro número
    if re.fullmatch(r"\d{8,20}", s):
        return s

    # URL eBay típica: /itm/287045152832 o .../itm/Title/287045152832
    # Acepta URLs con parámetros & (Powershell requiere comillas)
    m = re.search(r"/itm/(?:[^/]+/)?(\d{8,20})", s)
    if m:
        return m.group(1)

    # Algunas URLs llevan ?hash=item...
    m2 = re.search(r"(?:item=|hash=item)(\d{8,20})", s)
    if m2:
        return m2.group(1)

    raise ValueError("No pude extraer el ItemID. Pega la URL completa del listing de eBay o el número ItemID.")

def load_ebay_cfg() -> Dict[str, Any]:
    if not EBAY_YAML.exists():
        raise FileNotFoundError("No encuentro ebay.yaml en la carpeta SoftwareResell.")
    with open(EBAY_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    # Soporta formato:
    # api.ebay.com:
    # appid:
    # certid:
    # devid:
    # token:
    # marketplace:
    host = "api.ebay.com"
    if host not in cfg:
        # también acepto "api.ebay.com:" como top key
        # si no, intento usar el primer key
        if len(cfg.keys()) == 1:
            host = list(cfg.keys())[0]
        else:
            raise ValueError("ebay.yaml no tiene la clave api.ebay.com.")
    return {"host": host, **(cfg.get(host) or {})}

def ebay_trading_call(call_name: str, token: str, xml_body: str) -> str:
    url = "https://api.ebay.com/ws/api.dll"
    headers = {
        "X-EBAY-API-CALL-NAME": call_name,
        "X-EBAY-API-SITEID": "0", # US
        "X-EBAY-API-COMPATIBILITY-LEVEL": "967",
        "Content-Type": "text/xml",
    }
    # Trading API usa token dentro del XML
    r = requests.post(url, data=xml_body.encode("utf-8"), headers=headers, timeout=30)
    return r.text

def parse_trading_ack_and_error(xml: str) -> Tuple[str, str]:
    # super simple (sin librerías XML extra)
    ack = ""
    msg = ""
    m_ack = re.search(r"<Ack>(.*?)</Ack>", xml, flags=re.S)
    if m_ack:
        ack = m_ack.group(1).strip()
    # Error message largo
    m_long = re.search(r"<LongMessage>(.*?)</LongMessage>", xml, flags=re.S)
    if m_long:
        msg = clean_html(m_long.group(1))
    else:
        m_short = re.search(r"<ShortMessage>(.*?)</ShortMessage>", xml, flags=re.S)
        if m_short:
            msg = clean_html(m_short.group(1))
    return ack, msg

def get_item_from_ebay(item_id: str, token: str) -> Dict[str, Any]:
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  <DetailLevel>ReturnAll</DetailLevel>
  <IncludeItemSpecifics>true</IncludeItemSpecifics>
</GetItemRequest>"""

    xml = ebay_trading_call("GetItem", token, body)
    ack, msg = parse_trading_ack_and_error(xml)
    if ack != "Success" and ack != "Warning":
        raise RuntimeError(f"eBay respondió con Ack={ack}. Mensaje: {msg or 'Sin mensaje'}")

    # Extrae campos básicos de XML (rápido, sin parser pesado)
    def grab(tag: str) -> str:
        m = re.search(fr"<{tag}>(.*?)</{tag}>", xml, flags=re.S)
        return clean_html(m.group(1)).strip() if m else ""

    title = grab("Title")
    desc = grab("Description")

    price = ""
    m_price = re.search(r"<CurrentPrice[^>]*>(.*?)</CurrentPrice>", xml, flags=re.S)
    if m_price:
        price = clean_html(m_price.group(1)).strip()

    category = grab("CategoryName")
    condition = grab("ConditionDisplayName")
    brand = ""

    # Item specifics (NameValueList)
    specifics = {}
    for block in re.findall(r"<NameValueList>(.*?)</NameValueList>", xml, flags=re.S):
        n = re.search(r"<Name>(.*?)</Name>", block, flags=re.S)
        v = re.search(r"<Value>(.*?)</Value>", block, flags=re.S)
        if n and v:
            key = clean_html(n.group(1)).strip()
            val = clean_html(v.group(1)).strip()
            specifics[key] = val
            if key.lower() == "brand":
                brand = val

    # Fotos
    pics = []
    for p in re.findall(r"<PictureURL>(.*?)</PictureURL>", xml, flags=re.S):
        urlp = clean_html(p).strip()
        if urlp:
            pics.append(urlp)

    return {
        "item_id": item_id,
        "title": title,
        "description_html": desc,
        "description": clean_html(desc),
        "price": price,
        "category": category,
        "condition": condition,
        "brand": brand,
        "specifics": specifics,
        "pictures": pics,
        "raw_xml": xml, # debug
    }

def end_item_ebay(item_id: str, token: str, reason: str = "NotAvailable") -> None:
    body = f"""<?xml version="1.0" encoding="utf-8"?>
<EndItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  <EndingReason>{reason}</EndingReason>
</EndItemRequest>"""
    xml = ebay_trading_call("EndItem", token, body)
    ack, msg = parse_trading_ack_and_error(xml)
    if ack != "Success" and ack != "Warning":
        raise RuntimeError(f"EndItem falló. Ack={ack}. Mensaje: {msg or 'Sin mensaje'}")

# =========================
# DRAFT TEMPLATES
# =========================
def build_depop_draft(item: Dict[str, Any]) -> str:
    title = one_line(item["title"])[:80]
    price = item["price"]
    desc = item["description"].strip()
    specs = item.get("specifics", {}) or {}

    # hashtags suaves (sin inventar cosas)
    tags = []
    for k in ["Brand", "Color", "Size", "Style"]:
        if k in specs and specs[k]:
            tags.append(specs[k])

    hashtags = " ".join([f"#{re.sub(r'[^a-zA-Z0-9]', '', t).lower()}" for t in tags[:6] if t])

    # Depop suele ir más corto
    short = desc
    if len(short) > 550:
        short = short[:540].rsplit(" ", 1)[0] + "…"

    photos = item.get("pictures", [])[:8]

    lines = []
    lines.append("=== DEPOP DRAFT ===")
    lines.append(f"Título: {title}")
    lines.append(f"Precio: {price}")
    lines.append("")
    lines.append("Descripción (copia/pega):")
    lines.append(short)
    if hashtags.strip():
        lines.append("")
        lines.append("Hashtags sugeridos:")
        lines.append(hashtags)
    lines.append("")
    lines.append("Fotos (URLs):")
    for i, p in enumerate(photos, 1):
        lines.append(f"{i}. {p}")
    lines.append("")
    lines.append("Item specifics (referencia):")
    for k, v in specs.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines).strip()

def build_posh_draft(item: Dict[str, Any]) -> str:
    title = one_line(item["title"])[:80]
    price = item["price"]
    desc = item["description"].strip()
    specs = item.get("specifics", {}) or {}
    photos = item.get("pictures", [])[:16]

    # Campos útiles (si existen)
    brand = specs.get("Brand") or item.get("brand") or ""
    size = specs.get("Size") or specs.get("Waist Size") or ""
    color = specs.get("Color") or ""
    style = specs.get("Style") or ""
    material = specs.get("Material") or ""
    dept = specs.get("Department") or ""

    lines = []
    lines.append("=== POSHMARK DRAFT ===")
    lines.append(f"Título: {title}")
    lines.append(f"Precio: {price}")
    lines.append("")
    lines.append("Campos sugeridos:")
    lines.append(f"- Brand: {brand}")
    lines.append(f"- Size: {size}")
    lines.append(f"- Color: {color}")
    lines.append(f"- Style: {style}")
    lines.append(f"- Material: {material}")
    lines.append(f"- Department: {dept}")
    lines.append("")
    lines.append("Descripción (copia/pega):")
    lines.append(desc)
    lines.append("")
    lines.append("Fotos (URLs):")
    for i, p in enumerate(photos, 1):
        lines.append(f"{i}. {p}")
    lines.append("")
    lines.append("Item specifics (referencia):")
    for k, v in specs.items():
        lines.append(f"- {k}: {v}")
    return "\n".join(lines).strip()

# =========================
# CORE ACTIONS
# =========================
def crosslist_from_item(item_id: str, token: str) -> None:
    print(f"🔎 Buscando listing eBay ItemID={item_id} ...")
    item = get_item_from_ebay(item_id, token)

    # guarda debug JSON
    debug_json = {
        "item_id": item_id,
        "title": item["title"],
        "price": item["price"],
        "category": item["category"],
        "condition": item["condition"],
        "pictures": item["pictures"],
        "specifics": item["specifics"],
        "description": item["description"],
        "fetched_at": datetime.now().isoformat(),
    }
    debug_path = DRAFTS_DIR / f"ebay_{item_id}.json"
    save_json(debug_path, debug_json)

    depop_text = build_depop_draft(item)
    posh_text = build_posh_draft(item)

    stamp = now_stamp()
    depop_path = DRAFTS_DIR / f"draft_depop_{item_id}_{stamp}.txt"
    posh_path = DRAFTS_DIR / f"draft_posh_{item_id}_{stamp}.txt"

    depop_path.write_text(depop_text, encoding="utf-8")
    posh_path.write_text(posh_text, encoding="utf-8")

    # registra en map.json para futuro delist cruzado
    mp = load_json(MAP_PATH, {})
    mp.setdefault(item_id, {})
    mp[item_id]["last_crosslist_at"] = datetime.now().isoformat()
    save_json(MAP_PATH, mp)

    log_line(CROSSLIST_LOG, f"CROSSLIST | item_id={item_id} | depop={depop_path.name} | posh={posh_path.name}")
    print("\n✅ Drafts creados:")
    print(f" - {depop_path}")
    print(f" - {posh_path}")
    print(f" - {debug_path} (debug)")

def mark_sold(item_id: str, platform: str) -> None:
    # estado inventario
    state = load_json(STATE_PATH, {})
    state[item_id] = {"status": "SOLD", "sold_on": platform, "sold_at": datetime.now().isoformat()}
    save_json(STATE_PATH, state)
    log_line(ACCIONES_LOG, f"ITEM_SOLD | {item_id} | {platform} | {'SIMULADO' if MODO_PRUEBA else 'REAL'}")

def delist_everywhere(item_id: str, sold_on: str, token: str) -> None:
    """
    Delist seguro y oficial: eBay (sí).
    Depop/Posh: dejamos placeholders (manual guiado / futuro).
    """
    if sold_on.lower() != "ebay":
        # si se vendió fuera de eBay, bajamos eBay (oficial)
        if MODO_PRUEBA:
            print(f"🧪 SIMULADO: EndItem en eBay para ItemID={item_id}")
        else:
            print(f"🧨 Delist eBay (EndItem) ItemID={item_id} ...")
            end_item_ebay(item_id, token)
            print("✅ eBay delist OK")

    # placeholders
    if sold_on.lower() != "depop":
        print(f"ℹ️ Depop delist: (manual por ahora) ItemID={item_id}")
    if sold_on.lower() != "poshmark":
        print(f"ℹ️ Poshmark delist: (manual por ahora) ItemID={item_id}")

def usage() -> None:
    print("""
Uso:

1) Crosslist (ItemID o URL):
   python resell.py crosslist 287045152832
   python resell.py crosslist "https://www.ebay.com/itm/287045152832?..."

2) Marcar venta + delist (simula venta en otra plataforma):
   python resell.py sold 287045152832 depop
   python resell.py sold 287045152832 poshmark
   python resell.py sold 287045152832 ebay

3) Cambiar modo prueba (opcional):
   Edita MODO_PRUEBA = False en resell.py cuando estés listo.

Tips PowerShell:
- SI PEGAS URL con &, SIEMPRE entre comillas:
  python resell.py crosslist "https://www.ebay.com/itm/....&...."
""".strip())

def main():
    if len(sys.argv) < 3:
        usage()
        sys.exit(1)

    cmd = sys.argv[1].lower()
    cfg = load_ebay_cfg()
    token = cfg.get("token", "").strip()
    if not token:
        raise ValueError("Falta token en ebay.yaml")

    if cmd == "crosslist":
        item_id = extract_item_id(" ".join(sys.argv[2:]).strip())
        crosslist_from_item(item_id, token)
        return

    if cmd == "sold":
        item_id = extract_item_id(sys.argv[2])
        platform = sys.argv[3].strip().lower() if len(sys.argv) >= 4 else "ebay"
        print(f"📩 Venta recibida: item_id={item_id} platform={platform}")
        mark_sold(item_id, platform)
        delist_everywhere(item_id, platform, token)
        return

    usage()
    sys.exit(1)

if __name__ == "__main__":
    main()