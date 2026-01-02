import asyncio
from playwright.async_api import async_playwright
import os

async def borrar_en_poshmark(nombre_item):
    async with async_playwright() as p:
        ruta_perfil = os.path.join(os.getcwd(), "perfil_poshmark")
        
        context = await p.chromium.launch_persistent_context(
            user_data_dir=ruta_perfil,
            channel="chrome",
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )
        
        page = context.pages[0]
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        print(f"👔 Poshmark: Abriendo página...")
        # Esta URL no da error 404, te lleva a entrar a tu cuenta
        await page.goto("https://poshmark.com/login", wait_until="domcontentloaded")

        print("⚠️ POR FAVOR: Inicia sesión manualmente en la ventana que se abrió.")
        print("⏳ El bot esperará a que termines...")
        
        # El bot esperará 60 segundos para que tú pongas tu clave y entres
        await page.wait_for_timeout(60000) 

        await context.close()