"""Testa leitura, cache, tentativas e cópia sem tocar na rede."""
import threading
from types import SimpleNamespace

import pytest
from google.genai import errors
from pypdf import PdfWriter

import gemini_client
from cache import Cache
from gemini_client import ClienteGemini, escolher_flash
from organizer import copiar
from pdf_tools import listar_pdfs, ler_pdf
from pipeline import BAIXA, CACHE, ERRO, OK, analisar_um
from schema import MetadadosPDF

DADOS = {"titulo": "Teste", "autores": [{"nome": "Ana", "sobrenome": "Souza"}], "ano": 2021,
         "tipo_documento": "Teses", "area": "Física", "resumo_curto": "x", "confianca": 0.9}


def pdf(caminho, paginas=8):
    w = PdfWriter()
    for _ in range(paginas):
        w.add_blank_page(200, 200)
    w.add_metadata({"/Title": "Meta"})
    with open(caminho, "wb") as f:
        w.write(f)
    return caminho


class FakeModels:
    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.chamadas = 0

    def generate_content(self, **kw):
        self.chamadas += 1
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(parsed=MetadadosPDF(**r), text="",
                               usage_metadata=SimpleNamespace(total_token_count=100))


def cliente(respostas):
    c = ClienteGemini("chave-falsa", "modelo-x", rpm=6000)
    c.client = SimpleNamespace(models=FakeModels(respostas))
    return c


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(gemini_client, "_dormir", lambda s, c: None)


def test_ler_pdf_recorta_paginas(tmp_path):
    info = ler_pdf(pdf(tmp_path / "a.pdf"), n_paginas=3)
    assert info.paginas == 8 and info.titulo_meta == "Meta" and not info.erro
    assert info.recorte.startswith(b"%PDF")


def test_pdf_corrompido_vira_erro(tmp_path):
    (tmp_path / "ruim.pdf").write_bytes(b"isso nao e pdf")
    assert ler_pdf(tmp_path / "ruim.pdf").erro


def test_listar_ignora_pasta_saida(tmp_path):
    pdf(tmp_path / "a.pdf")
    (tmp_path / "sub").mkdir(); pdf(tmp_path / "sub" / "b.pdf")
    (tmp_path / "out").mkdir(); pdf(tmp_path / "out" / "c.pdf")
    assert [p.name for p in listar_pdfs(tmp_path, False)] == ["a.pdf"]
    assert [p.name for p in listar_pdfs(tmp_path, True, tmp_path / "out")] == ["a.pdf", "b.pdf"]


def test_retry_429_depois_sucesso_e_cache(tmp_path):
    erro = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"}]}})
    c = cliente([erro, DADOS])
    cache = Cache(tmp_path / "c.sqlite")
    p = pdf(tmp_path / "a.pdf")
    ev = threading.Event()
    r = analisar_um(p, c, cache, 5, ev)
    assert r.status == OK and r.dados.sobrenome_principal == "Souza"
    assert c.client.models.chamadas == 2 and c.tokens_usados == 100
    r2 = analisar_um(p, c, cache, 5, ev)          # segunda vez: cache, sem chamada
    assert r2.status == CACHE and c.client.models.chamadas == 2
    c.client.models.respostas.append(DADOS)
    analisar_um(p, c, cache, 5, ev, usar_cache=False)  # reanálise força chamada
    assert c.client.models.chamadas == 3


def test_erro_definitivo_nao_entra_em_loop(tmp_path):
    erro = errors.ClientError(401, {"error": {"code": 401, "message": "bad key"}})
    c = cliente([erro])
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), 5, threading.Event())
    assert r.status == ERRO and "Chave recusada" in r.erro
    assert c.client.models.chamadas == 1


def test_429_persistente_sem_reserva_desiste(tmp_path):
    erro = errors.ClientError(429, {"error": {"code": 429, "message": "quota"}})
    c = cliente([erro] * 10)
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), 5, threading.Event())
    assert r.status == ERRO and c.client.models.chamadas == 2


def test_troca_de_modelo_em_503_e_404(tmp_path):
    e503 = errors.ServerError(503, {"error": {"code": 503, "message": "high demand"}})
    e404 = errors.ClientError(404, {"error": {"code": 404, "message": "not found"}})
    c = cliente([e503, e503, e404, DADOS])
    c.candidatos = ["m1", "m2", "m3"]; c.modelo = "m1"
    avisos = []; c.ao_aviso = avisos.append
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), 5, threading.Event())
    assert r.status == OK and c.modelo == "m3" and c.client.models.chamadas == 4
    assert any("trocando para m2" in a for a in avisos)


def test_timeout_conta_como_temporario(tmp_path):
    import httpx
    c = cliente([httpx.ReadTimeout("lento"), DADOS])
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), 5, threading.Event())
    assert r.status == OK


def test_baixa_confianca(tmp_path):
    c = cliente([{**DADOS, "confianca": 0.3}])
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), 5, threading.Event())
    assert r.status == BAIXA


def test_ordenar_flash():
    from gemini_client import ordenar_flash
    nomes = ["gemini-2.5-flash", "gemini-flash-latest", "gemini-flash-lite-latest",
             "gemini-3-flash-preview", "gemini-3.1-flash-lite", "gemini-3.5-flash",
             "gemini-3.8-flash", "gemini-3.8-flash-tts", "gemini-3.1-flash-image", "gemini-2.5-pro"]
    assert ordenar_flash(nomes) == ["gemini-3.8-flash", "gemini-3.5-flash", "gemini-2.5-flash",
                                    "gemini-flash-latest", "gemini-3.1-flash-lite",
                                    "gemini-flash-lite-latest"]
    assert escolher_flash(["gemini-pro"]) is None


def test_copiar_sem_sobrescrever(tmp_path):
    a, b = pdf(tmp_path / "a.pdf"), pdf(tmp_path / "b.pdf", 2)
    destino = tmp_path / "saida"
    r = copiar([(a, "Teses", "X.pdf"), (b, "Teses", "X")], destino)
    nomes = sorted(p.name for p in (destino / "Teses").iterdir())
    assert nomes == ["X (2).pdf", "X.pdf"] and not r["erros"] and r["log"].exists()
    assert a.exists() and b.exists()  # originais intactos


def test_cota_diaria_troca_na_hora_e_memoria(tmp_path):
    diaria = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "66697s"}]}})
    c = cliente([diaria, DADOS])
    c.memoria = tmp_path / "ultimo.txt"
    c.candidatos = ["m1", "m2"]; c.modelo = "m1"
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), 5, threading.Event())
    assert r.status == OK and c.client.models.chamadas == 2 and c.modelo == "m2"
    assert c.memoria.read_text() == "m2"
