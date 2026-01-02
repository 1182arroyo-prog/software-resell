# crosslist.py
# Uso:
# python crosslist.py "URL_DE_EBAY"
#
# Requiere:
# - generar_drafts.py (ya te funciona)
# - internet
#
# Qué hace:
# 1) Intenta extraer ItemID desde la URL
# 2) Si no puede, abre el link y busca el ItemID en el HTML
# 3) Ejecuta generar_drafts.py con el ItemID

import re
import sys
import subprocess
import requests

def extract_item_id_from_text(text: str) -> str | None:
    # patrones comunes de item id en HTML
    patterns = [
        r'"legacyItemId"\s*:\s*"(\d{9,})"',
        r'"itemId"\s*:\s*"(\d{9,})"',
        r'item=(\d{9,})',
        r'/itm/(?:[^/]+/)?(\d{9,})',
        r'\b(\d{12})\b', # fallback 12 dígitos típico
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if m:
            return m.group(1)
    return None

def extract_item_id(url: str) -> str:
    url = url.strip()

    # Intento 1: URL típica /itm/...
    m = re.search(r"/itm/(?:[^/]+/)?(\d{9,})", url)
    if m:
        return m.group(1)

    # Intento 2: parámetro item=
    m = re.search(r"[?&]item=(\d{9,})", url)
    if m:
        return m.group(1)

    # Intento 3: cualquier número largo en la URL
    m = re.search(r"(\d{9,})", url)
    if m:
        return m.group(1)

    # Intento 4: abrir el link y sacar el item id del HTML
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()

    item_id = extract_item_id_from_text(r.text)
    if item_id:
        return item_id

    raise ValueError(
        "No pude extraer el ItemID de ese enlace.\n"
        "Tip: la URL del listing normalmente se ve como:\n"
        "https://www.ebay.com/itm/123456789012"
    )

def main():
    if len(sys.argv) < 2:
        print('Uso: python crosslist.py "URL_DE_EBAY"')
        sys.exit(1)

    url = sys.argv[1]
    item_id = extract_item_id(url)

    print(f"✅ ItemID detectado: {item_id}")
    print("🚀 Generando drafts...")

    result = subprocess.run([sys.executable, "generar_drafts.py", item_id])
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()