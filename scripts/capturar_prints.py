"""Prints do README contra a demo real (opcional; requer Playwright para Python).

    <python com playwright> scripts/capturar_prints.py [--url http://127.0.0.1:5410/]

Executa cada cenário antes de fotografar (job, explain, comparação, avanço). Escreve no
banco configurado: use só na demo, nunca durante uma apresentação.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:5410/")
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)


def aba(pg, nome):
    pg.get_by_role("button", name=nome, exact=True).click()
    pg.wait_for_timeout(600)


def foto(pg, nome, seletor=None):
    alvo = pg.locator(seletor).first if seletor else pg
    alvo.screenshot(path=str(OUT / nome)) if seletor else pg.screenshot(path=str(OUT / nome), full_page=True)
    print("ok", nome)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
    pg.goto(a.url)
    pg.wait_for_selector(".resultado", timeout=60000)
    pg.select_option("select >> nth=3", "20")       # sexta, 20:00
    pg.wait_for_timeout(2500)
    pg.screenshot(path=str(OUT / "01-consulta-eta.png"))
    print("ok 01-consulta-eta.png")
    foto(pg, "02-grade-dow-turno.png", "[role=tabpanel]")

    aba(pg, "Raw vs Materializado")
    pg.get_by_role("button", name="Executar as duas").click()
    pg.wait_for_selector(".veredito", timeout=120000)
    foto(pg, "03-raw-vs-materializado.png", "[role=tabpanel]")

    aba(pg, "Simples × Incremental")
    pg.get_by_role("button", name="Rodar os dois desenhos").click()
    pg.wait_for_selector(".veredito", timeout=600000)
    foto(pg, "04-simples-vs-incremental.png", "[role=tabpanel]")

    aba(pg, "Job e janela")
    pg.get_by_role("button", name="Rodar job").click()
    pg.wait_for_selector(".run", timeout=240000)
    pg.wait_for_timeout(1500)
    foto(pg, "05-job-e-janela.png", "[role=tabpanel]")

    aba(pg, "Config")
    foto(pg, "06-config.png", "[role=tabpanel]")

    aba(pg, "Por baixo do capô")
    pg.wait_for_selector("table", timeout=60000)
    pg.locator("details.gaveta summary").first.click()
    pg.wait_for_timeout(500)
    foto(pg, "07-por-baixo-do-capo.png", "[role=tabpanel]")
    b.close()
