from datetime import datetime
from pathlib import Path

LOG_FILE = Path("logs/acciones.log")

def log_accion(evento: str, sku: str, platform: str, modo: str) -> None:
    LOG_FILE.parent.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    linea = f"{timestamp} | {evento} | {sku} | {platform} | {modo}\n"
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(linea)