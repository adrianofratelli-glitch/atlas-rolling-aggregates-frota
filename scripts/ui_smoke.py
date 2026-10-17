"""Smoke visual da UI (opcional): abas, console, overflow e 3 viewports.

Requer Playwright para Python (não é dependência da POV):
    <python com playwright> scripts/ui_smoke.py [--url http://127.0.0.1:8410] [--out /tmp/frota-shots]
Não altera dados, exceto se `--acoes` (roda job, injeta atraso, avança 1 dia).
"""
from __future__ import annotations

import argparse
import sys

from playwright.sync_api import sync_playwright

ABAS = ["Consulta ETA", "Raw vs Materializado", "Simples × Incremental", "Job e janela", "Config",
        "Por baixo do capô"]

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:8410/")
ap.add_argument("--out", default="/tmp/frota-shots")
ap.add_argument("--acoes", action="store_true")
a = ap.parse_args()
falhas = []
with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in [(1440, 1000), (768, 1024), (360, 800)]:
        pg = b.new_page(viewport={"width": w, "height": h})
        erros = []
        pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(a.url)
        pg.wait_for_selector(".resultado", timeout=60000)
        for aba in ABAS:
            pg.get_by_role("button", name=aba, exact=True).click()
            pg.wait_for_timeout(500)
            if aba == "Raw vs Materializado":
                pg.get_by_role("button", name="Executar as duas").click()
                pg.wait_for_selector(".veredito", timeout=60000)
            if a.acoes and w == 1440 and aba == "Job e janela":
                pg.get_by_role("button", name="Rodar job").click()
                pg.wait_for_selector(".run", timeout=240000)
                pg.get_by_role("button", name="Injetar").click()
                pg.wait_for_timeout(800)
                pg.get_by_role("button", name="Rodar job").click()
                pg.wait_for_selector(".run", timeout=240000)
                pg.get_by_role("button", name="Avançar 1 dia").click()
                pg.wait_for_selector('button:has-text("Avançar 1 dia"):not([disabled])', timeout=240000)
            if a.acoes and w == 1440 and aba == "Simples × Incremental":
                pg.get_by_role("button", name="Rodar os dois desenhos").click()
                pg.wait_for_selector(".veredito", timeout=240000)
                if "mesmo agregado" not in pg.locator(".veredito").inner_text():
                    falhas.append("simples × incremental: agregados diferentes")
            larg = pg.evaluate("document.documentElement.scrollWidth")
            if larg > w + 1:
                falhas.append(f"{w}px {aba}: overflow horizontal ({larg}px)")
            nome = aba.lower().replace(" ", "-").replace("/", "").replace("$", "")
            pg.screenshot(path=f"{a.out}/{w}-{nome}.png", full_page=True)
        if erros:
            falhas.append(f"{w}px console: {erros[:3]}")
        pg.close()
    b.close()
print("\n".join(falhas) if falhas else "ok: 6 abas × 3 viewports, sem erro de console nem overflow")
sys.exit(1 if falhas else 0)
