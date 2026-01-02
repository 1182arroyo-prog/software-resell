import csv
import asyncio
from pathlib import Path
from Cerebro_v2 import procesar_evento

COLA = Path("cola_ventas.csv")
PROCESADAS = Path("logs/cola_procesada.csv")

async def main():
    if not COLA.exists():
        print("❌ No existe cola_ventas.csv")
        return

    with open(COLA, "r", encoding="utf-8", newline="") as f:
        filas = list(csv.DictReader(f))

    if not filas:
        print("📭 No hay ventas en cola.")
        return

    pendientes = []
    for fila in filas:
        sku = (fila.get("sku") or "").strip()
        platform = (fila.get("platform") or "").strip().lower()
        if sku and platform:
            pendientes.append({"sku": sku, "platform": platform})

    if not pendientes:
        print("📭 No hay filas válidas en cola.")
        return

    for v in pendientes:
        evento = {"event": "ITEM_SOLD", "platform": v["platform"], "sku": v["sku"]}
        await procesar_evento(evento)
        _guardar_procesada(v["sku"], v["platform"])

    with open(COLA, "w", encoding="utf-8", newline="") as f:
        f.write("sku,platform\n")

    print("✅ Cola procesada y limpiada.")

def _guardar_procesada(sku, platform):
    PROCESADAS.parent.mkdir(exist_ok=True)
    existe = PROCESADAS.exists()
    with open(PROCESADAS, "a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if not existe:
            w.writerow(["sku", "platform"])
        w.writerow([sku, platform])

if __name__ == "__main__":
    asyncio.run(main())