"""
Conversão de e-books (EPUB, MOBI, AZW3, FB2) para PDF.

Usa o PyMuPDF, que abre esses formatos sozinho, sem precisar instalar o
Calibre. O PDF gerado fica guardado em .cache/convertidos, com o hash do
e-book no nome: converter de novo o mesmo livro não gasta tempo.
"""

import threading
import time
from pathlib import Path

import pymupdf

from registro import log

# E-books costumam citar fontes que não vêm dentro do arquivo. O MuPDF avisa cada
# uma no terminal, mas troca por uma fonte padrão e converte normalmente.
pymupdf.TOOLS.mupdf_display_errors(False)

EXTENSOES_EBOOK = {".epub", ".mobi", ".azw3", ".fb2"}

# Página A4 em pontos. Sem isto, o MuPDF usa uma página pequena, de leitor de bolso.
LARGURA, ALTURA, FONTE = 595, 842, 11

# O MuPDF não foi feito para várias threads ao mesmo tempo; um livro de cada vez.
_trava = threading.Lock()


class ErroConversao(Exception):
    """O e-book não pôde ser convertido (corrompido, com DRM, formato não suportado)."""


def eh_ebook(caminho: Path) -> bool:
    return caminho.suffix.lower() in EXTENSOES_EBOOK


def converter(origem: Path, sha256: str, pasta: Path) -> Path:
    """Devolve o caminho do PDF convertido, convertendo só se ainda não existir."""
    destino = pasta / f"{sha256}.pdf"
    if destino.exists():
        return destino
    pasta.mkdir(parents=True, exist_ok=True)

    with _trava:
        inicio = time.monotonic()
        try:
            livro = pymupdf.open(origem)
        except Exception as erro:
            raise ErroConversao(f"não abriu ({erro})") from erro
        try:
            if livro.needs_pass:
                raise ErroConversao("protegido (DRM ou senha)")
            if livro.is_reflowable:
                livro.layout(width=LARGURA, height=ALTURA, fontsize=FONTE)
            if livro.page_count == 0:
                raise ErroConversao("nenhuma página depois da conversão")

            pdf = pymupdf.open("pdf", livro.convert_to_pdf())
            # Só o que existe: campo vazio vira "NullObject" quando lido pelo pypdf,
            # e isso chegaria à IA como se fosse o título.
            meta = livro.metadata or {}
            pdf.set_metadata({k: meta[k] for k in ("title", "author") if meta.get(k)})
            try:
                pdf.set_toc(livro.get_toc())   # o sumário vira marcadores do PDF
            except Exception:
                pass   # sumário malformado não deve impedir a conversão

            # Grava num temporário e renomeia: se cair no meio, não sobra PDF pela metade.
            temporario = destino.with_suffix(".tmp")
            pdf.save(temporario, garbage=3, deflate=True)
            pdf.close()
            temporario.replace(destino)
            log.info("Convertido para PDF em %.1f s: %s", time.monotonic() - inicio, origem.name)
        except ErroConversao as erro:
            log.warning("Não converteu %s: %s", origem.name, erro)
            raise
        except Exception as erro:
            log.warning("Não converteu %s: %s", origem.name, erro)
            raise ErroConversao(str(erro)[:150]) from erro
        finally:
            livro.close()
    return destino
