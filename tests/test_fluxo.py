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
from organizer import ItemCopia, copiar
from pdf_tools import listar_arquivos, ler_pdf
from pipeline import BAIXA, CACHE, ERRO, OK, Processador, analisar_um
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


def test_listar_ignora_pasta_saida_e_lixo(tmp_path):
    pdf(tmp_path / "a.pdf")
    (tmp_path / "nota.docx").write_bytes(b"x")
    (tmp_path / "Thumbs.db").write_bytes(b"x")
    (tmp_path / "~$nota.docx").write_bytes(b"x")
    (tmp_path / "sub").mkdir(); pdf(tmp_path / "sub" / "b.pdf")
    (tmp_path / "out").mkdir(); pdf(tmp_path / "out" / "c.pdf")
    assert [p.name for p in listar_arquivos(tmp_path, False)] == ["a.pdf", "nota.docx"]
    assert [p.name for p in listar_arquivos(tmp_path, True, tmp_path / "out")] == [
        "a.pdf", "nota.docx", "b.pdf"]


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
    r = copiar([ItemCopia(a, "Teses", "X.pdf"), ItemCopia(b, "Teses", "X")], destino)
    nomes = sorted(p.name for p in (destino / "Teses").iterdir())
    assert nomes == ["X (2).pdf", "X.pdf"] and not r["erros"] and r["log"].exists()
    assert a.exists() and b.exists()  # originais intactos


def test_copiar_duvidas_para_verificar(tmp_path):
    a, b = pdf(tmp_path / "a.pdf"), pdf(tmp_path / "b.pdf", 2)
    destino = tmp_path / "saida"
    copiar([ItemCopia(a, "Livros", "Bom.pdf"), ItemCopia(b, "Sem análise", "b.pdf", True)],
           destino)
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


def epub(caminho, titulo="Memórias póstumas", autor="Machado de Assis"):
    """Um EPUB mínimo, mas válido, com três capítulos."""
    import zipfile
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:'
                   'tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="c.opf" '
                   'media-type="application/oebps-package+xml"/></rootfiles></container>')
        itens = "".join(f'<item id="c{i}" href="c{i}.xhtml" media-type="application/xhtml+xml"/>'
                        for i in range(3))
        ordem = "".join(f'<itemref idref="c{i}"/>' for i in range(3))
        z.writestr("c.opf",
                   '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" '
                   'version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/'
                   f'dc/elements/1.1/"><dc:title>{titulo}</dc:title><dc:creator>{autor}'
                   '</dc:creator><dc:identifier id="id">x</dc:identifier></metadata>'
                   f'<manifest>{itens}</manifest><spine>{ordem}</spine></package>')
        for i in range(3):
            z.writestr(f"c{i}.xhtml",
                       '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/'
                       f'1999/xhtml"><body><h1>Capítulo {i + 1}</h1>'
                       + "<p>Ao verme que primeiro roeu as frias carnes.</p>" * 60
                       + "</body></html>")
    return caminho


def test_ebook_e_convertido_e_analisado(tmp_path):
    livro = epub(tmp_path / "livro.epub")
    c = cliente([DADOS], FLASHES)
    r = analisar_um(livro, c, Cache(tmp_path / "c.sqlite"), NORMAL, threading.Event(),
                    pasta_convertidos=tmp_path / "conv")
    assert r.status == OK and r.convertido and r.convertido.exists()
    info = ler_pdf(r.convertido)
    assert info.titulo_meta == "Memórias póstumas" and "Capítulo 1" in info.texto
    # Na segunda vez vem do cache, mas o PDF convertido continua disponível para a cópia.
    r2 = analisar_um(livro, c, Cache(tmp_path / "c.sqlite"), NORMAL, threading.Event(),
                     pasta_convertidos=tmp_path / "conv")
    assert r2.status == CACHE and r2.convertido == r.convertido


def test_ebook_corrompido_vira_erro_sem_chamar_ia(tmp_path):
    (tmp_path / "ruim.mobi").write_bytes(b"nao e um mobi")
    c = cliente([DADOS], FLASHES)
    r = analisar_um(tmp_path / "ruim.mobi", c, Cache(tmp_path / "c.sqlite"), NORMAL,
                    threading.Event(), escalar=True, pasta_convertidos=tmp_path / "conv")
    assert r.status == ERRO and "converter" in r.erro and c.client.models.chamadas == 0


def test_copia_de_ebook_leva_pdf_e_original_com_o_mesmo_nome(tmp_path):
    livro = epub(tmp_path / "livro.epub")
    convertido = pdf(tmp_path / "conv.pdf")
    destino = tmp_path / "saida"
    (destino / "Livros").mkdir(parents=True)
    (destino / "Livros" / "Assis-Memórias.pdf").write_bytes(b"ja existia")
    r = copiar([ItemCopia(livro, "Livros", "Assis-Memórias.pdf", False, convertido)], destino)
    nomes = sorted(p.name for p in (destino / "Livros").iterdir())
    assert nomes == ["Assis-Memórias (2).epub", "Assis-Memórias (2).pdf", "Assis-Memórias.pdf"]
    assert not r["erros"] and r["copiados"][0]["original_copiado_em"].endswith("(2).epub")


def test_outros_formatos_mantem_nome_e_extensao(tmp_path):
    (tmp_path / "Foto.JPG").write_bytes(b"x")
    (tmp_path / "LEIAME").write_bytes(b"x")
    destino = tmp_path / "saida"
    copiar([ItemCopia(tmp_path / "Foto.JPG", "Outros formatos", "Foto.JPG", True),
            ItemCopia(tmp_path / "LEIAME", "Outros formatos", "LEIAME", True)], destino)
    pasta = destino / ".verificar" / "Outros formatos"
    assert sorted(p.name for p in pasta.iterdir()) == ["Foto.jpg", "LEIAME"]


def test_janela_e_avisada_da_conversao_do_ebook(tmp_path, monkeypatch):
    import pipeline
    monkeypatch.setattr(pipeline.analisar_um, "__defaults__",
                        pipeline.analisar_um.__defaults__[:-1] + (tmp_path / "conv",))
    livro = epub(tmp_path / "livro.epub")
    p = Processador(cliente([DADOS], FLASHES), Cache(tmp_path / "c.sqlite"), NORMAL, 1)
    p._analisar_um_e_avisar(livro)
    tipos = [(tipo, carga) for _, tipo, carga in list(p.fila.queue)]
    assert tipos[0][0] == "etapa" and tipos[0][1][0] == livro
    assert tipos[1][0] == "resultado" and tipos[1][1].status == OK


def test_listas_limpam_repetidos_e_mantem_outros(tmp_path):
    import listas
    arquivo = tmp_path / "listas.json"
    listas.salvar(listas.Listas([" Partituras ", "partituras", "", "Livros"], ["Música"]), arquivo)
    lido = listas.carregar(arquivo)
    assert lido.categorias == ["Partituras", "Livros", "Outros"]
    assert lido.areas == ["Música"]
    arquivo.write_text("{estragado", encoding="utf-8")
    assert listas.carregar(arquivo) == listas.Listas()   # volta ao padrão, sem quebrar


def test_ia_recebe_as_categorias_da_pessoa(tmp_path):
    from google.genai import _transformers
    c = cliente([dict(DADOS, tipo_documento="Partituras")], FLASHES)
    c.categorias = ["Partituras", "Livros", "Outros"]
    esquema = c._config(NIVEIS[NORMAL], FLASHES[0]).response_schema
    enum = _transformers.t_schema(None, esquema).properties["tipo_documento"].enum
    assert enum == ["Partituras", "Livros", "Outros"]


def test_categoria_fora_da_lista_vira_outros_e_cache_antigo_continua_valendo(tmp_path):
    from schema import para_texto_simples
    dados = MetadadosPDF(**dict(DADOS, tipo_documento="Teses"))
    assert para_texto_simples(dados, ["Livros", "Outros"]).tipo_documento == "Outros"
    cache = Cache(tmp_path / "c.sqlite")
    cache.salvar("x", "m", dados)   # "Teses" removida da lista depois: o cache ainda lê
    assert cache.obter("x").dados.tipo_documento == "Teses"


def test_salvar_chave_troca_so_a_linha_da_chave(tmp_path):
    import config
    env = tmp_path / ".env"
    env.write_text("# comentario\nGEMINI_API_KEY=velha\nGEMINI_RPM=10\n", encoding="utf-8")
    config.salvar_chave("  nova123456789  ", env)
    assert env.read_text(encoding="utf-8") == ("# comentario\nGEMINI_API_KEY=nova123456789\n"
                                               "GEMINI_RPM=10\n")
    assert config.chave_mascarada("nova123456789") == "nova…6789"
    sem_env = tmp_path / "outro" / ".env"
    sem_env.parent.mkdir()
    config.salvar_chave("abc", sem_env)
    assert sem_env.read_text(encoding="utf-8") == "GEMINI_API_KEY=abc\n"


def test_escolha_do_python_vai_para_o_env_sem_mexer_no_resto(tmp_path):
    import config
    env = tmp_path / ".env"
    env.write_text("GEMINI_API_KEY=abc\nGEMINI_RPM=10\n", encoding="utf-8")
    config.salvar_no_env("PYTHON", r"C:\Python312\python.exe", env)
    assert env.read_text(encoding="utf-8").splitlines() == [
        r"PYTHON=C:\Python312\python.exe", "GEMINI_API_KEY=abc", "GEMINI_RPM=10"]
    config.salvar_no_env("PYTHON", "", env)   # volta para o automático
    assert "PYTHON=" in env.read_text(encoding="utf-8").splitlines()


def test_python_atual_passa_no_teste_e_inexistente_nao(tmp_path):
    import sys
    from pathlib import Path
    import pythons
    teste = pythons.testar(Path(sys.executable))
    assert teste.ok and teste.versao.startswith("3.") and not teste.faltando
    assert not pythons.testar(tmp_path / "python.exe").ok
    assert all("windowsapps" not in str(p).lower() for p in pythons.candidatos())


def test_configs_antigas_da_raiz_vao_para_a_pasta_config(tmp_path, monkeypatch):
    import config
    monkeypatch.setattr(config, "PASTA_DO_PROJETO", tmp_path)
    monkeypatch.setattr(config, "PASTA_CONFIG", tmp_path / "config")
    (tmp_path / ".env").write_text("GEMINI_API_KEY=velha\n", encoding="utf-8")
    (tmp_path / "listas.json").write_text("{}", encoding="utf-8")
    config.migrar_da_raiz()
    assert (tmp_path / "config" / ".env").read_text(encoding="utf-8") == "GEMINI_API_KEY=velha\n"
    assert (tmp_path / "config" / "listas.json").exists()
    assert not (tmp_path / ".env").exists() and not (tmp_path / "listas.json").exists()
    # Se já existe em config/, o da raiz não sobrescreve nada.
    (tmp_path / ".env").write_text("GEMINI_API_KEY=outra\n", encoding="utf-8")
    config.migrar_da_raiz()
    assert "velha" in (tmp_path / "config" / ".env").read_text(encoding="utf-8")
    assert (tmp_path / ".env").exists()
