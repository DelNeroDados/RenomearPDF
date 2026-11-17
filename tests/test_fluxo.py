"""Testa leitura, cache, tentativas e cópia sem tocar na rede."""
import threading
from types import SimpleNamespace

import pytest
from google.genai import errors
from pypdf import PdfWriter

import gemini_client
import pdf_tools
from cache import Cache
from config import NIVEIS
from gemini_client import ClienteGemini, escolher_flash, ordenar_modelos
from organizer import copiar
from pdf_tools import listar_pdfs, ler_pdf
from pipeline import BAIXA, CACHE, ERRO, OK, analisar_um
from schema import MetadadosPDF

NORMAL, CAPRICHADO = 1, 2

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
        self.pedidos = []   # (modelo, thinking_level ou None)

    def generate_content(self, **kw):
        self.chamadas += 1
        pensar = kw["config"].thinking_config
        self.pedidos.append((kw["model"], pensar.thinking_level if pensar else None))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return SimpleNamespace(parsed=MetadadosPDF(**r), text="",
                               usage_metadata=SimpleNamespace(total_token_count=100))


def cliente(respostas, disponiveis=None):
    """Sem `disponiveis`, usa um modelo fixo; com, deixa o cliente escolher pela fila."""
    c = ClienteGemini("chave-falsa", "" if disponiveis else "modelo-x", rpm=6000)
    if disponiveis:
        c.disponiveis = disponiveis
    c.client = SimpleNamespace(models=FakeModels(respostas))
    return c


FLASHES = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash"]


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
    r = analisar_um(p, c, cache, NORMAL, ev)
    assert r.status == OK and r.dados.sobrenome_principal == "Souza"
    assert c.client.models.chamadas == 2 and c.tokens_usados == 100
    r2 = analisar_um(p, c, cache, NORMAL, ev)          # segunda vez: cache, sem chamada
    assert r2.status == CACHE and c.client.models.chamadas == 2
    c.client.models.respostas.append(DADOS)
    analisar_um(p, c, cache, NORMAL, ev, usar_cache=False)  # reanálise força chamada
    assert c.client.models.chamadas == 3


def test_erro_definitivo_nao_entra_em_loop(tmp_path):
    erro = errors.ClientError(401, {"error": {"code": 401, "message": "bad key"}})
    c = cliente([erro])
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL, threading.Event())
    assert r.status == ERRO and "Chave recusada" in r.erro
    assert c.client.models.chamadas == 1


def test_429_persistente_sem_reserva_desiste(tmp_path):
    erro = errors.ClientError(429, {"error": {"code": 429, "message": "quota"}})
    c = cliente([erro] * 10)
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL, threading.Event())
    assert r.status == ERRO and c.client.models.chamadas == 2


def test_troca_de_modelo_em_503_e_404(tmp_path):
    e503 = errors.ServerError(503, {"error": {"code": 503, "message": "high demand"}})
    e404 = errors.ClientError(404, {"error": {"code": 404, "message": "not found"}})
    c = cliente([e503, e503, e404, DADOS], FLASHES)
    avisos = []; c.ao_aviso = avisos.append
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL,
                    threading.Event())
    assert r.status == OK and r.modelo == "gemini-3.5-flash" and c.client.models.chamadas == 4
    assert any("trocando para gemini-3.6-flash" in a for a in avisos)


def test_timeout_conta_como_temporario(tmp_path):
    import httpx
    c = cliente([httpx.ReadTimeout("lento"), DADOS])
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL, threading.Event())
    assert r.status == OK


def test_baixa_confianca(tmp_path):
    c = cliente([{**DADOS, "confianca": 0.3}])
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL, threading.Event())
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
    r = copiar([(a, "Teses", "X.pdf", False), (b, "Teses", "X", False)], destino)
    nomes = sorted(p.name for p in (destino / "Teses").iterdir())
    assert nomes == ["X (2).pdf", "X.pdf"] and not r["erros"] and r["log"].exists()
    assert a.exists() and b.exists()  # originais intactos


def test_copiar_duvidas_para_verificar(tmp_path):
    a, b = pdf(tmp_path / "a.pdf"), pdf(tmp_path / "b.pdf", 2)
    destino = tmp_path / "saida"
    copiar([(a, "Livros", "Bom.pdf", False), (b, "Sem análise", "b.pdf", True)], destino)
    assert (destino / "Livros" / "Bom.pdf").exists()
    assert (destino / ".verificar" / "Sem análise" / "b.pdf").exists()


def test_cota_diaria_troca_na_hora_e_memoria(tmp_path):
    diaria = errors.ClientError(429, {"error": {"code": 429, "message": "quota", "details": [
        {"@type": "type.googleapis.com/google.rpc.QuotaFailure", "violations": [
            {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "66697s"}]}})
    c = cliente([diaria, DADOS], FLASHES[:2])
    c.memoria = tmp_path / "sem_cota.json"
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL,
                    threading.Event())
    assert r.status == OK and c.client.models.chamadas == 2 and r.modelo == "gemini-3.6-flash"
    # No dia seguinte (outra sessão), o modelo sem cota é pulado sem gastar chamada.
    outro = cliente([], FLASHES[:2]); outro.memoria = c.memoria
    assert outro._sem_cota_hoje() == {"gemini-3.8-flash"}


def test_fila_depende_do_nivel():
    nomes = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3.5-pro", "gemini-2.5-pro"]
    assert ordenar_modelos(nomes, NIVEIS[0].familias)[0] == "gemini-3.5-flash-lite"
    assert ordenar_modelos(nomes, NIVEIS[NORMAL].familias) == ["gemini-3.8-flash",
                                                               "gemini-3.5-flash-lite"]
    assert ordenar_modelos(nomes, NIVEIS[3].familias)[:2] == ["gemini-3.5-pro", "gemini-2.5-pro"]


def test_duvida_e_refeita_no_nivel_acima(tmp_path):
    c = cliente([{**DADOS, "confianca": 0.2}, DADOS], FLASHES)
    cache = Cache(tmp_path / "c.sqlite")
    p = pdf(tmp_path / "a.pdf", 12)
    r = analisar_um(p, c, cache, NORMAL, threading.Event(), escalar=True)
    assert r.status == OK and r.nivel == CAPRICHADO
    assert [nivel for _, nivel in c.client.models.pedidos] == ["LOW", "HIGH"]
    # Já foi tentado no Caprichado: pedir Normal de novo vem do cache, sem chamada.
    assert analisar_um(p, c, cache, NORMAL, threading.Event(), escalar=True).status == CACHE
    assert c.client.models.chamadas == 2


def test_escalada_fica_com_o_melhor(tmp_path):
    c = cliente([{**DADOS, "confianca": 0.5, "titulo": "Primeira"},
                 {**DADOS, "confianca": 0.3, "titulo": "Segunda"}], FLASHES)
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL,
                    threading.Event(), escalar=True)
    assert r.status == BAIXA and r.dados.titulo == "Primeira"


def test_sem_escalar_nao_repete(tmp_path):
    c = cliente([{**DADOS, "confianca": 0.2}], FLASHES)
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL,
                    threading.Event(), escalar=False)
    assert r.status == BAIXA and c.client.models.chamadas == 1


def test_cache_de_nivel_menor_nao_serve(tmp_path):
    cache = Cache(tmp_path / "c.sqlite")
    p = pdf(tmp_path / "a.pdf")
    analisar_um(p, cliente([DADOS], FLASHES), cache, 0, threading.Event())
    c = cliente([DADOS], FLASHES)
    r = analisar_um(p, c, cache, CAPRICHADO, threading.Event())
    assert r.status == OK and c.client.models.chamadas == 1


def test_modelo_sem_raciocinio_repete_sem_ele(tmp_path):
    recusa = errors.ClientError(400, {"error": {"code": 400,
                                                "message": "Thinking level is not supported"}})
    c = cliente([recusa, DADOS], FLASHES)
    r = analisar_um(pdf(tmp_path / "a.pdf"), c, Cache(tmp_path / "c.sqlite"), NORMAL,
                    threading.Event())
    assert r.status == OK
    assert c.client.models.pedidos == [("gemini-3.8-flash", "LOW"), ("gemini-3.8-flash", None)]


def test_recorte_que_falha_nao_impede_o_texto(tmp_path, monkeypatch):
    def quebra(*_):
        raise RecursionError("maximum recursion depth exceeded")
    monkeypatch.setattr(pdf_tools, "_recortar", quebra)
    info = ler_pdf(pdf(tmp_path / "a.pdf"), 3)
    assert not info.erro and info.recorte == b"" and info.paginas == 8


def test_cache_antigo_sem_coluna_nivel(tmp_path):
    import sqlite3
    banco = tmp_path / "c.sqlite"
    con = sqlite3.connect(banco)
    con.execute("CREATE TABLE analises (sha256 TEXT PRIMARY KEY, modelo TEXT, dados TEXT,"
                " criado_em TEXT DEFAULT CURRENT_TIMESTAMP)")
    con.execute("INSERT INTO analises (sha256, modelo, dados) VALUES ('x', 'm', ?)",
                (MetadadosPDF(**DADOS).model_dump_json(),))
    con.commit(); con.close()
    guardado = Cache(banco).obter("x")
    assert guardado.nivel == 1 and guardado.dados.titulo == "Teste"
