import asyncio
from playwright.async_api import async_playwright
import os

async def borrar_en_depop(nombre_item):
    async with async_playwright() as p:
        ruta_perfil = os.path.join(os.getcwd(), "perfil_depop")
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=ruta_perfil,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = context.pages[0]
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        print(f"🤖 Depop: Entrando al inventario...")
        
        try:
            # CAMBIO AQUÍ: 'domcontentloaded' es mucho más rápido que 'networkidle'
            await page.goto("https://www.depop.com/products/manage/", wait_until="domcontentloaded", timeout=60000)
            
            print(f"🔍 Buscando: {nombre_item}")
            # Esperamos a la barra de búsqueda específicamente
            search_bar = page.locator('input[id*="search"], [role="searchbox"]').first
            await search_bar.wait_for(state="visible", timeout=20000)
            
            await search_bar.fill(nombre_item)
            await page.keyboard.press("Enter")
            
            print(f"✅ Búsqueda realizada.")
            await page.wait_for_timeout(5000) # Tiempo para que veas el resultado
            
        except Exception as e:
            print(f"❌ Error en Depop: {e}")

        await context.close()
