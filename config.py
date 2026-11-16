"""
Configurações do programa, lidas do arquivo .env (ou de variáveis de ambiente).

Só GEMINI_API_KEY é obrigatória. As demais têm valores padrão pensados para a
chave gratuita; veja o .env.example para a explicação de cada uma.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PASTA_DO_PROJETO = Path(__file__).resolve().parent
PASTA_CACHE = PASTA_DO_PROJETO / ".cache"

MODELO_NOME_PADRAO = "{area}-{sobrenome}-{ano}-{titulo}"


@dataclass
class Config:
    api_key: str
    modelo: str
    rpm: int
    workers: int
    paginas: int
    modelo_nome: str


def carregar() -> Config:
    """Uma variável de ambiente do sistema vence o que estiver escrito no .env."""
    arquivo = _ler_env(PASTA_DO_PROJETO / ".env")

    def ler(chave, padrao=""):
        return os.environ.get(chave) or arquivo.get(chave, padrao)

    return Config(
        api_key=ler("GEMINI_API_KEY"),
        modelo=ler("GEMINI_MODEL"),
        rpm=_inteiro(ler("GEMINI_RPM"), 10),
        workers=_inteiro(ler("GEMINI_WORKERS"), 4),
        paginas=_inteiro(ler("PDF_PAGINAS"), 5),
        modelo_nome=ler("MODELO_NOME") or MODELO_NOME_PADRAO,
    )


def _ler_env(caminho: Path) -> dict:
    """
    Lê linhas CHAVE=valor. É tão simples que não vale instalar o python-dotenv
    só para isso.
    """
    valores = {}
    if not caminho.exists():
        return valores
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        chave, _, valor = linha.partition("=")
        valores[chave.strip()] = valor.strip().strip('"').strip("'")
    return valores


def _inteiro(valor, padrao: int) -> int:
    """Converte para inteiro positivo; se vier lixo, usa o padrão em vez de quebrar."""
    try:
        return max(1, int(valor))
    except (TypeError, ValueError):
        return padrao
