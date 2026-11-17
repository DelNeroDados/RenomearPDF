"""
Leitura dos PDFs no próprio computador, sem internet.

Daqui saem três coisas para cada arquivo: uma impressão digital (hash) para o
cache, o texto das primeiras páginas e um PDF pequeno, só com essas páginas,
que é o que de fato vai para o Gemini.
"""

import hashlib
import io
import logging
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader, PdfWriter

# O pypdf reclama muito de PDFs mal formados que ele mesmo consegue ler.
# Esses avisos só poluem o terminal.
logging.getLogger("pypdf").setLevel(logging.ERROR)

# O Gemini aceita até uns 20 MB enviados direto na requisição. Deixamos folga.
LIMITE_ENVIO_DIRETO = 15 * 1024 * 1024


@dataclass
class InfoPDF:
    caminho: Path
    sha256: str
    paginas: int = 0
    titulo_meta: str = ""
    autor_meta: str = ""
    texto: str = ""        # pode vir vazio em PDF escaneado, e tudo bem
    recorte: bytes = b""   # PDF só com as primeiras páginas
    erro: str = ""


# Arquivos que o Windows e o Office criam sozinhos; não são documentos de ninguém.
LIXO_DO_SISTEMA = {"thumbs.db", "desktop.ini", ".ds_store"}


def listar_arquivos(pasta: Path, recursivo: bool, ignorar: Path | None = None) -> list[Path]:
    """
    Todos os arquivos da pasta (PDFs, e-books e o resto), em ordem alfabética.

    `ignorar` serve para pular a pasta de saída. Sem isso, rodar o programa duas
    vezes na mesma pasta faria ele analisar as próprias cópias.
    """
    ignorar = ignorar.resolve() if ignorar else None
    encontrados = []
    for arquivo in pasta.glob("**/*" if recursivo else "*"):
        if not arquivo.is_file() or arquivo.name.lower() in LIXO_DO_SISTEMA:
            continue
        if arquivo.name.startswith("~$"):   # temporário de documento aberto no Office
            continue
        if ignorar and ignorar in arquivo.resolve().parents:
            continue
        encontrados.append(arquivo)
    return sorted(encontrados, key=lambda p: str(p).lower())


def eh_pdf(caminho: Path) -> bool:
    return caminho.suffix.lower() == ".pdf"


def hash_arquivo(caminho: Path) -> str:
    """SHA-256 do conteúdo. Lido em blocos para não carregar livros inteiros na memória."""
    h = hashlib.sha256()
    with open(caminho, "rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def ler_pdf(caminho: Path, n_paginas: int = 5, sha256: str = "") -> InfoPDF:
    """
    Abre o PDF e separa o que interessa. Nunca levanta exceção: se der problema,
    devolve o InfoPDF com `erro` preenchido, e a linha aparece vermelha na tela.
    """
    info = InfoPDF(caminho=caminho, sha256=sha256 or hash_arquivo(caminho))
    try:
        leitor = PdfReader(str(caminho))
        if leitor.is_encrypted and not _tentar_abrir_sem_senha(leitor):
            info.erro = "PDF protegido por senha"
            return info

        info.paginas = len(leitor.pages)
        metadados = leitor.metadata or {}
        info.titulo_meta = str(metadados.get("/Title") or "").strip()
        info.autor_meta = str(metadados.get("/Author") or "").strip()

        quantas = min(n_paginas, info.paginas)
        info.texto = _extrair_texto(leitor, quantas)
    except Exception as erro:
        info.erro = f"Falha ao ler PDF: {erro}"[:200]
        return info

    try:
        info.recorte = _recortar(leitor, quantas)
    except Exception:
        pass   # sem o recorte, o Gemini recebe só o texto extraído
    return info


def texto_preview(caminho: Path, n_paginas: int = 3) -> str:
    """Texto das primeiras páginas, separado por página, para o painel 'Ver texto'."""
    try:
        leitor = PdfReader(str(caminho))
        blocos = []
        for i in range(min(n_paginas, len(leitor.pages))):
            texto = leitor.pages[i].extract_text() or ""
            if texto.strip():
                blocos.append(f"--- PÁGINA {i + 1} ---\n{texto}")
        return "\n\n".join(blocos) or "(Sem texto extraível: provavelmente PDF escaneado.)"
    except Exception as erro:
        return f"Erro ao ler: {erro}"


def _tentar_abrir_sem_senha(leitor: PdfReader) -> bool:
    # Muitos PDFs vêm "criptografados" só para bloquear impressão, com senha vazia.
    try:
        leitor.decrypt("")
        return True
    except Exception:
        return False


def _extrair_texto(leitor: PdfReader, quantas: int) -> str:
    partes = []
    for i in range(quantas):
        try:
            partes.append(leitor.pages[i].extract_text() or "")
        except Exception:
            pass   # uma página quebrada não deve derrubar as outras
    return "\n".join(partes).strip()


def _recortar(leitor: PdfReader, quantas: int) -> bytes:
    """
    Monta um PDF novo só com as primeiras páginas. Mandar o livro inteiro
    gastaria muito mais tokens sem ajudar: capa, folha de rosto e ficha
    catalográfica estão sempre no começo.
    """
    escritor = PdfWriter()
    for i in range(quantas):
        # Sem os links: num livro com sumário clicável, copiar a página puxava as
        # páginas de destino de cada link, e assim por diante, até estourar a recursão.
        escritor.add_page(leitor.pages[i], excluded_keys=("/Annots", "/B"))
    buffer = io.BytesIO()
    escritor.write(buffer)
    recorte = buffer.getvalue()
    # Páginas escaneadas em alta resolução podem passar do limite; aí vai só o texto.
    return recorte if len(recorte) <= LIMITE_ENVIO_DIRETO else b""
