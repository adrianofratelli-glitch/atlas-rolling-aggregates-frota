"""Smoke visual da UI (opcional): os 7 passos do roteiro em 1440/768/360 px.

Requer Playwright para Python (não é dependência da POV):
    <python com playwright> scripts/ui_smoke.py [--url http://127.0.0.1:5410/] [--out /tmp/frota-shots]

Escreve no banco que a API estiver usando: roda o job (passo 3, só em 1440 px) e persiste
um cenário em `consultas_salvas` (passo 5). Aponte a API para um banco `*_test`; use
`--sem-escrita` para pular as duas ações. Nunca aperta "Resetar demo".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PASSOS = ["Dado bruto e schema", "A regra", "Gerar a base", "Consultar cenários",
          "Fora da base", "Quando atualiza", "Poucas amostras"]
LONGO = 120_000

ap = argparse.ArgumentParser()
ap.add_argument("--url", default="http://127.0.0.1:5410/")
ap.add_argument("--out", default="/tmp/frota-shots")
ap.add_argument("--sem-escrita", action="store_true")
a = ap.parse_args()
Path(a.out).mkdir(parents=True, exist_ok=True)
falhas: list[str] = []


def checar(cond: bool, msg: str) -> None:
    if not cond:
        falhas.append(msg)


def passo(pg, n: int, w: int) -> None:
    if n == 1:
        pg.wait_for_selector(".cartao table tbody tr", timeout=LONGO)
    elif n == 2:
        pg.wait_for_selector(".janela", timeout=LONGO)
    elif n == 3 and w == 1440 and not a.sem_escrita:
        pg.get_by_role("button", name="Rodar job agora").click()
        pg.wait_for_selector(".pipeline li.destaque", timeout=LONGO)
        checar("materialized view" in pg.locator(".pipeline li.destaque").inner_text(),
               "passo 3: $merge sem a frase da materialized view")
    elif n == 4:
        pg.wait_for_selector(".resultado .selo", timeout=LONGO)
        checar("Job diário" in pg.locator(".resultado .selo").inner_text(), "passo 4: selo não é Job diário")
        pg.get_by_text("Ver query / chamada executada").first.click()
        checar(pg.locator(".gaveta[open] pre mark").count() > 0, "passo 4: gaveta sem operador destacado")
    elif n == 5:
        if not a.sem_escrita:
            pg.get_by_label("persistir este resultado").check()
        pg.get_by_role("button", name="Calcular").click()
        pg.wait_for_selector(".resultado .selo.sob_demanda", timeout=LONGO)
        pg.wait_for_selector('button:has-text("Calcular"):not([disabled])', timeout=LONGO)
        if not a.sem_escrita:
            pg.get_by_role("button", name="Calcular").click()
            pg.wait_for_function(
                "() => document.querySelector('.selo-detalhe')?.textContent.includes('lido do salvo')",
                timeout=LONGO)
            checar("lido do salvo" in pg.locator(".selo-detalhe").inner_text(),
                   "passo 5: segundo cálculo não leu do salvo")
    elif n == 6:
        pg.wait_for_selector(".previa", timeout=LONGO)
        pg.wait_for_selector(".cartao table tbody tr", timeout=LONGO)
    elif n == 7:
        pg.wait_for_selector(".niveis li.ativo", timeout=LONGO)
        opcao = pg.locator(".filtro select").first.evaluate("s => s.options[s.selectedIndex].text")
        checar("poucos dados" in opcao, f"passo 7: não abriu num trecho esparso ({opcao})")


with sync_playwright() as p:
    b = p.chromium.launch()
    for w, h in [(1440, 1000), (768, 1024), (360, 800)]:
        pg = b.new_page(viewport={"width": w, "height": h})
        erros: list[str] = []
        pg.on("console", lambda m: erros.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: erros.append(str(e)))
        pg.goto(a.url.split("#")[0] + "#passo=1")
        pg.wait_for_selector(".passo-cab h2", timeout=LONGO)
        for n, titulo in enumerate(PASSOS, start=1):
            if n > 1:
                pg.get_by_role("button", name=f"Próximo: {titulo} →").click()
            pg.wait_for_function(f"() => location.hash === '#passo={n}'")
            checar(pg.locator(".trilho [aria-current='step']").get_attribute("aria-label").startswith(f"{n} "),
                   f"{w}px passo {n}: aria-current no item errado")
            passo(pg, n, w)
            pg.wait_for_timeout(400)
            larg = pg.evaluate("document.documentElement.scrollWidth")
            checar(larg <= w, f"{w}px passo {n}: overflow horizontal ({larg}px)")
            pg.screenshot(path=f"{a.out}/{w}-passo{n}.png", full_page=True)
        checar(not erros, f"{w}px console: {erros[:3]}")
        pg.close()
    b.close()
print("\n".join(falhas) if falhas else "ok: 7 passos × 3 viewports, sem erro de console nem overflow")
sys.exit(1 if falhas else 0)
