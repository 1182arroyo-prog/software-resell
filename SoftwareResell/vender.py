import sys
import asyncio

from Cerebro_v2 import procesar_evento

def mostrar_uso():
    print("Uso:")
    print(" python vender.py <SKU> <platform>")
    print("Ejemplo:")
    print(" python vender.py SKU-DEMO-123 ebay")

async def main():
    if len(sys.argv) != 3:
        mostrar_uso()
        return

    sku = sys.argv[1]
    platform = sys.argv[2].lower()

    if platform not in ["ebay", "depop", "poshmark"]:
        print("❌ Plataforma inválida. Usa: ebay, depop, poshmark")
        return

    evento = {
        "event": "ITEM_SOLD",
        "platform": platform,
        "sku": sku
    }

    await procesar_evento(evento)

if __name__ == "__main__":
    asyncio.run(main())