# generar_drafts.py
# Uso:
# python generar_drafts.py 287045152832
#
# Requiere:
# pip install requests pyyaml

from __future__ import annotations

import re
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

import requests
import yaml

DRAFTS_DIR = Path("drafts")


# ----------------------------
# Utilidades
# ----------------------------

def _now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")

def _norm(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

def _strip_html(html: str) -> str:
    # quita tags básicos
    if not html:
        return ""
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"</p\s*>", "\n", html, flags=re.IGNORECASE)
    html = re.sub(r"<[^>]+>", "", html)
    # decode entidades comunes
    html = html.replace("&nbsp;", " ").replace("&amp;", "&")
    html = html.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return _norm(html)

def _first_nonempty(*vals: str) -> str:
    for v in vals:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def _hashtags_from_text(*parts: str, limit: int = 18) -> List[str]:
    raw = " ".join([p for p in parts if p])
    raw = raw.lower().replace("&", "and")
    raw = re.sub(r"[^a-z0-9\s]", " ", raw)
    words = [w for w in raw.split() if 2 <= len(w) <= 18]

    stop = {
        "the", "and", "for", "with", "mens", "men", "women", "womens", "size",
        "new", "like", "condition", "no", "not", "very", "good", "great", "nice"
    }
    words = [w for w in words if w not in stop]

    seen = set()
    uniq: List[str] = []
    for w in words:
        if w not in seen:
            seen.add(w)
            uniq.append(w)

    tags: List[str] = []
    for w in uniq:
        if w.isdigit():
            continue
        tags.append("#" + w)
        if len(tags) >= limit:
            break
    return tags


# ----------------------------
# Cargar config ebay.yaml
# ----------------------------

def load_yaml_config(path: str = "ebay.yaml") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe {path}. Debe estar en la misma carpeta.")
    with open(p, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}

    # Tu yaml parece:
    # api.ebay.com:
    # appid:
    # certid:
    # devid:
    # token:
    # marketplace: "EBAY_US"
    #
    # Tomamos la primera key principal (ej: api.ebay.com)
    if len(cfg.keys()) == 1:
        root_key = next(iter(cfg.keys()))
        inner = cfg.get(root_key) or {}
    else:
        # si algún día lo cambias a formato plano, también funciona
        inner = cfg

    token = inner.get("token") or ""
    if not token:
        raise ValueError("Falta token en ebay.yaml (token: ...).")

    return {
        "endpoint_key": next(iter(cfg.keys())) if cfg else "api.ebay.com",
        "token": token.strip(),
        "siteid": "0", # eBay US
        "compat_level": "967",
        "marketplace": inner.get("marketplace", "EBAY_US"),
    }


# ----------------------------
# eBay Trading API - GetItem
# ----------------------------

def ebay_get_item(item_id: str, token: str, siteid: str = "0", compat_level: str = "967") -> Dict[str, Any]:
    url = "https://api.ebay.com/ws/api.dll"

    headers = {
        "X-EBAY-API-CALL-NAME": "GetItem",
        "X-EBAY-API-SITEID": siteid,
        "X-EBAY-API-COMPATIBILITY-LEVEL": compat_level,
        "Content-Type": "text/xml",
    }

    body = f"""<?xml version="1.0" encoding="utf-8"?>
<GetItemRequest xmlns="urn:ebay:apis:eBLBaseComponents">
  <RequesterCredentials>
    <eBayAuthToken>{token}</eBayAuthToken>
  </RequesterCredentials>
  <ItemID>{item_id}</ItemID>
  <IncludeItemSpecifics>true</IncludeItemSpecifics>
  <DetailLevel>ReturnAll</DetailLevel>
</GetItemRequest>"""

    r = requests.post(url, headers=headers, data=body.encode("utf-8"), timeout=45)
    r.raise_for_status()

    # parse “simple” sin librerías externas: extraemos campos por regex / xml básica
    text = r.text

    def x(tag: str) -> str:
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", text, flags=re.DOTALL)
        return _norm(m.group(1)) if m else ""

    ack = x("Ack")
    if ack and ack.lower() != "success" and ack.lower() != "warning":
        long_msg = x("LongMessage") or x("ShortMessage") or "Error desconocido"
        raise RuntimeError(f"eBay respondió con Ack={ack}. Mensaje: {long_msg}")

    # Title / Description (Description suele venir en <Description> con HTML)
    title = x("Title")
    desc_html = ""
    mdesc = re.search(r"<Description[^>]*>(.*?)</Description>", text, flags=re.DOTALL)
    if mdesc:
        desc_html = mdesc.group(1).strip()

    # Precio
    # <CurrentPrice currencyID="USD">34.99</CurrentPrice> o <StartPrice ...>
    price = ""
    currency = ""
    mprice = re.search(r'<CurrentPrice[^>]*currencyID="([^"]+)">([^<]+)</CurrentPrice>', text)
    if not mprice:
        mprice = re.search(r'<StartPrice[^>]*currencyID="([^"]+)">([^<]+)</StartPrice>', text)
    if mprice:
        currency = mprice.group(1).strip()
        price = mprice.group(2).strip()

    # Condición
    condition = x("ConditionDisplayName") or x("ConditionDescription")

    # Fotos
    photos: List[str] = []
    pics = re.findall(r"<PictureURL[^>]*>(.*?)</PictureURL>", text, flags=re.DOTALL)
    for p in pics:
        u = p.strip()
        if u:
            photos.append(u)

    # Item Specifics (NameValueList)
    item_specifics: Dict[str, str] = {}
    # Captura pares <Name>Brand</Name> ... <Value>Lee</Value>
    blocks = re.findall(r"<NameValueList>(.*?)</NameValueList>", text, flags=re.DOTALL)
    for b in blocks:
        n = re.search(r"<Name>(.*?)</Name>", b, flags=re.DOTALL)
        v = re.search(r"<Value>(.*?)</Value>", b, flags=re.DOTALL)
        if n and v:
            name = _norm(n.group(1))
            val = _norm(v.group(1))
            if name and val and name not in item_specifics:
                item_specifics[name] = val

    # Category info
    category = x("PrimaryCategoryID") or x("CategoryID")

    return {
        "item_id": item_id,
        "title": title,
        "description_html": desc_html,
        "description_text": _strip_html(desc_html),
        "price": price,
        "currency": currency,
        "condition": condition,
        "photos": photos,
        "category": category,
        "itemSpecifics": item_specifics,
    }


# ----------------------------
# Draft builders
# ----------------------------

def _pick_spec(item: Dict[str, Any], keys: List[str]) -> str:
    specs = item.get("itemSpecifics") or {}
    for k in keys:
        v = specs.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""

def build_depop_draft(item: Dict[str, Any]) -> str:
    title = _norm(item.get("title", ""))
    price = _norm(str(item.get("price", "")))
    currency = _norm(item.get("currency", ""))
    condition = _norm(item.get("condition", ""))

    brand = _norm(_pick_spec(item, ["Brand"]))
    size = _norm(_pick_spec(item, ["Size", "Size Type", "Waist Size", "Inseam"]))
    color = _norm(_pick_spec(item, ["Color", "Colour"]))
    material = _norm(_pick_spec(item, ["Material", "Fabric Type"]))
    style = _norm(_pick_spec(item, ["Style", "Fit", "Type"]))
    dept = _norm(_pick_spec(item, ["Department"]))

    desc = _norm(item.get("description_text", ""))

    lines: List[str] = []
    lines.append(title)

    meta1 = " | ".join([x for x in [
        f"Brand: {brand}" if brand else "",
        f"Size: {size}" if size else "",
        f"Color: {color}" if color else ""
    ] if x])
    if meta1:
        lines.append("🧷 " + meta1)

    meta2 = " | ".join([x for x in [
        f"Material: {material}" if material else "",
        f"Style/Fit: {style}" if style else "",
        f"Dept: {dept}" if dept else ""
    ] if x])
    if meta2:
        lines.append("📌 " + meta2)

    if price:
        p = f"{currency} {price}".strip()
        lines.append(f"💵 Price: {p}")

    if condition:
        lines.append("✅ Condition: " + condition)

    if desc:
        short = desc[:450]
        lines.append("")
        lines.append("📝 Details:")
        lines.append(short)

    tags = _hashtags_from_text(title, brand, color, material, style, dept, limit=18)
    if tags:
        lines.append("")
        lines.append(" ".join(tags))

    lines.append("")
    lines.append("📦 Ships fast. Message me for bundle deals.")

    return "\n".join(lines)

def build_posh_draft(item: Dict[str, Any]) -> str:
    title = _norm(item.get("title", ""))
    price = _norm(str(item.get("price", "")))
    currency = _norm(item.get("currency", ""))
    condition = _norm(item.get("condition", ""))
    desc = _norm(item.get("description_text", ""))

    brand = _norm(_pick_spec(item, ["Brand"]))
    size = _norm(_pick_spec(item, ["Size", "Waist Size", "Inseam"]))
    color = _norm(_pick_spec(item, ["Color", "Colour"]))
    material = _norm(_pick_spec(item, ["Material", "Fabric Type"]))
    dept = _norm(_pick_spec(item, ["Department"]))
    style = _norm(_pick_spec(item, ["Style", "Fit", "Type"]))

    lines: List[str] = []
    lines.append(title)

    if brand:
        lines.append(f"Brand: {brand}")
    if size:
        lines.append(f"Size: {size}")
    if color:
        lines.append(f"Color: {color}")
    if material:
        lines.append(f"Material: {material}")
    if style:
        lines.append(f"Style/Fit: {style}")
    if dept:
        lines.append(f"Department: {dept}")

    if price:
        p = f"{currency} {price}".strip()
        lines.append(f"Price: {p}")
    if condition:
        lines.append(f"Condition: {condition}")

    if desc:
        lines.append("")
        lines.append("Description:")
        lines.append(desc[:900])

    lines.append("")
    lines.append("Bundle to save on shipping ✨")

    return "\n".join(lines)

def extract_top_photos(item: Dict[str, Any], n: int = 4) -> List[str]:
    photos = item.get("photos") or []
    photos = [p for p in photos if isinstance(p, str) and p.strip()]
    return photos[:n]


# ----------------------------
# MAIN
# ----------------------------

def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("Uso: python generar_drafts.py ITEM_ID")
        print("Ejemplo: python generar_drafts.py 287045152832")
        return

    item_id = sys.argv[1].strip()

    cfg = load_yaml_config("ebay.yaml")
    token = cfg["token"]

    print(f"🔎 Buscando listing eBay ItemID={item_id} ...")
    item = ebay_get_item(item_id, token)

    # Guardamos un json por si quieres debug
    DRAFTS_DIR.mkdir(exist_ok=True)
    json_path = DRAFTS_DIR / f"ebay_{item_id}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(item, f, ensure_ascii=False, indent=2)

    # Fotos top (solo como lista para copiar/pegar)
    top_photos = extract_top_photos(item, n=4)

    stamp = _now_stamp()
    depop_path = DRAFTS_DIR / f"draft_depop_{item_id}_{stamp}.txt"
    posh_path = DRAFTS_DIR / f"draft_posh_{item_id}_{stamp}.txt"

    depop_txt = build_depop_draft(item)
    posh_txt = build_posh_draft(item)

    # anexamos fotos al final (copy/paste fácil)
    if top_photos:
        depop_txt += "\n\n📸 Top Photos (copy links):\n" + "\n".join(top_photos)
        posh_txt += "\n\n📸 Photos (copy links):\n" + "\n".join(item.get("photos", []))

    with open(depop_path, "w", encoding="utf-8") as f:
        f.write(depop_txt)

    with open(posh_path, "w", encoding="utf-8") as f:
        f.write(posh_txt)

    print("\n✅ Drafts creados:")
    print(f" - {depop_path}")
    print(f" - {posh_path}")
    print(f" - {json_path} (debug)")


if __name__ == "__main__":
    main()