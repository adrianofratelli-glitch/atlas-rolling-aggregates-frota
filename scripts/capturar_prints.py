"""Prints do README (1440 px) contra a demo que a API estiver servindo.

Requer Playwright para Python (não é dependência da POV):
    <python com playwright> scripts/capturar_prints.py [--url http://127.0.0.1:5410/]

Só leitura: navega pelos passos, consulta cenários e abre gavetas. No passo 4 calcula um
veículo na raw **desmarcando** "guardar o resultado". Nunca clica "Rodar job agora" nem
"Resetar demo": pode rodar contra o banco da demo, mas não durante uma apresentação.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
LONGO = 120_000

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:5410/")
a = ap.parse_args()
OUT.mkdir(parents=True, exist_ok=True)
falhas: list[str] = []


def ir(pg, n: int) -> None:
    pg.goto(a.url.split("#")[0] + f"#passo={n}")
    pg.wait_for_function(f"() => location.hash === '#passo={n}'")
    pg.wait_for_selector(".passo-cab h2", timeout=LONGO)


def foto(pg, nome: str) -> None:
    pg.evaluate("() => { window.scrollTo(0, 0); document.querySelectorAll('*').forEach(e => { if (e.scrollTop) e.scrollTop = 0; }); }")
    pg.wait_for_timeout(600)
    alvo = pg.locator(".chip-alvo")
    if alvo.count() == 0 or "Atlas" not in alvo.inner_text():
        falhas.append(f"{nome}: chip do alvo não mostra Atlas")
    pg.screenshot(path=str(OUT / nome), full_page=True)
    print("ok", nome)


def abrir_gaveta(pg) -> None:
    pg.get_by_text("Ver query / chamada executada").first.click()
    pg.wait_for_selector(".gaveta[open] pre", timeout=LONGO)


with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)

    ir(pg, 1)
    pg.wait_for_selector(".colecao[open] .campos-desc", timeout=LONGO)
    foto(pg, "01-collections-e-schema.png")

    ir(pg, 3)
    pg.wait_for_selector(".acao button.primario", timeout=LONGO)
    pg.get_by_text("Ver o script do Atlas Trigger").click()
    pg.wait_for_selector(".gaveta[open] pre", timeout=LONGO)
    foto(pg, "03-gerar-a-base.png")

    ir(pg, 4)
    pg.wait_for_selector(".resultado .selo", timeout=LONGO)
    abrir_gaveta(pg)
    foto(pg, "04-consultar-cenarios.png")

    # veículo específico: vai à raw; desmarca "guardar" para não escrever na demo
    pg.locator("select[name=veiculoId]").select_option(index=7)
    guardar = pg.get_by_label("guardar o resultado")
    if not guardar.is_checked():
        falhas.append("passo 4: 'guardar o resultado' deveria vir marcado")
    guardar.uncheck()
    pg.get_by_role("button", name="Calcular").click()
    pg.wait_for_selector(".resultado .selo.sob_demanda", timeout=LONGO)
    pg.wait_for_selector('button:has-text("Calcular"):not([disabled])', timeout=LONGO)
    foto(pg, "04-consultar-veiculo.png")

    ir(pg, 5)
    pg.wait_for_selector(".previa", timeout=LONGO)
    pg.wait_for_selector(".cartao table tbody tr", timeout=LONGO)
    foto(pg, "05-quando-atualiza.png")
    b.close()

print("\n".join(falhas) if falhas else "ok: prints em docs/screenshots/")
sys.exit(1 if falhas else 0)
