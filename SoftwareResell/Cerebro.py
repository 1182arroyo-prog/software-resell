import asyncio
from Sincronizador import borrar_en_depop 
from SincronizadorPosh import borrar_en_poshmark # <--- Nueva importación
import requests

EBAY_TOKEN = "v^1.1#i^1#p^3#f^0#r^0#I^3#t^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" 

async def iniciar_programa():
    print("📡 Conectando con eBay para sincronizar TODO...")
    
    # Supongamos que vendiste el Tommy (o lo que eBay diga)
    item_vendido = "Tommy jeans bax loose tapered mens 38x30"
    
    print(f"🛍️ Venta detectada: {item_vendido}")
    
    # EL TRÍO EN ACCIÓN:
    print("1️⃣ Iniciando limpieza en Depop...")
    await borrar_en_depop(item_vendido)
    
    print("2️⃣ Iniciando limpieza en Poshmark...")
    await borrar_en_poshmark(item_vendido)
    
    print("✨ ¡Sincronización total completada!")

if __name__ == "__main__":
    asyncio.run(iniciar_programa())