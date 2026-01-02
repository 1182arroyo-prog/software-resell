from config import SECRET_KEY
import asyncio
from inventory.state import marcar_vendido

from Sincronizador import borrar_en_depop
from SincronizadorPosh import borrar_en_poshmark

from logger import log_accion

# ✅ Seguro por defecto:
# True = NO borra nada (solo simula)
# False = habilita borrado REAL (pero con confirmación humana)
MODO_PRUEBA = True


def confirmar_borrado(sku: str, platform: str) -> bool:
    print("\n⚠️ ATENCIÓN ⚠️")
    print(f"Vas a BORRAR REALMENTE en otras plataformas por venta en: {platform}")
    print(f"SKU: {sku}")
    confirmacion = input("Escribe SI para continuar (cualquier otra cosa cancela): ")
    return confirmacion.strip().upper() == "SI"


async def procesar_evento(evento: dict):
    print("🧠 Cerebro v2 activo")
    print(f"📩 Evento recibido: {evento}")

    # Validación mínima
    if "event" not in evento or "platform" not in evento or "sku" not in evento:
        print("❌ Evento inválido. Debe incluir: event, platform, sku")
        return

    if evento["event"] != "ITEM_SOLD":
        print("ℹ️ Evento ignorado (no es ITEM_SOLD)")
        return

    sku = str(evento["sku"]).strip()
    platform = str(evento["platform"]).strip().lower()

    if platform not in ["ebay", "depop", "poshmark"]:
        print("❌ Plataforma inválida. Usa: ebay, depop, poshmark")
        return

    # 1) Guardar estado
    marcar_vendido(sku, platform)
    print("💾 Estado actualizado (SOLD)")

    # 2) Log (siempre, incluso en simulado)
    modo = "SIMULADO" if MODO_PRUEBA else "REAL"
    log_accion("ITEM_SOLD", sku, platform, modo)

    # 3) Determinar qué plataformas limpiar (no borres donde se vendió)
    limpiar_depop = platform != "depop"
    limpiar_posh = platform != "poshmark"

    # 4) Modo seguro (simulación)
    if MODO_PRUEBA:
        print("🟡 MODO_PRUEBA = True → NO se borra nada.")
        if limpiar_depop:
            print(f"🧪 SIMULADO: Delist en Depop para SKU: {sku}")
        if limpiar_posh:
            print(f"🧪 SIMULADO: Delist en Poshmark para SKU: {sku}")
        return

    # 5) Confirmación humana obligatoria
    if not confirmar_borrado(sku, platform):
        print("❌ Borrado cancelado por el usuario.")
        return

    # 6) Delist REAL
    tareas = []
    if limpiar_depop:
        print("🧹 Delist REAL en Depop...")
        tareas.append(borrar_en_depop(sku))

    if limpiar_posh:
        print("🧹 Delist REAL en Poshmark...")
        tareas.append(borrar_en_poshmark(sku))

    await asyncio.gather(*tareas)
    print("✅ Delist cruzado REAL completado")


async def main():
    evento_demo = {
        "event": "ITEM_SOLD",
        "platform": "ebay",
        "sku": "SKU-DEMO-123"
    }
    await procesar_evento(evento_demo)


if __name__ == "__main__":
    asyncio.run(main())