import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from limpar_atlas import selecionar_bancos  # noqa: E402


def test_selecao_allowlist():
    nomes = ["frota_eta", "frota_eta_bench", "frota_eta_test", "frota_eta_dst_test",
             "frota_eta_fixtures", "frota_eta2_test", "frota_etafoo_test", "other_db_test"]
    assert selecionar_bancos(nomes) == ["frota_eta_bench", "frota_eta_dst_test", "frota_eta_test"]


def test_demo_nunca_selecionada_mesmo_com_env(monkeypatch):
    from frota import settings
    monkeypatch.setattr(settings, "MONGODB_DB", "outro")
    assert "frota_eta" not in selecionar_bancos(["frota_eta", "outro", "frota_eta_test"])
