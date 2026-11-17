"""
Configurações do programa, lidas de config/.env (ou de variáveis de ambiente).

Só GEMINI_API_KEY é obrigatória. As demais têm valores padrão pensados para a
chave gratuita; veja o config/.env.example para a explicação de cada uma.

Tudo o que é da pessoa (chave, Python escolhido, listas) fica na pasta config/;
o log fica em logs/ e as análises guardadas em .cache/.
"""

import os
from dataclasses import dataclass
from pathlib import Path

PASTA_DO_PROJETO = Path(__file__).resolve().parent
PASTA_CACHE = PASTA_DO_PROJETO / ".cache"
PASTA_CONFIG = PASTA_DO_PROJETO / "config"
ARQUIVO_ENV = PASTA_CONFIG / ".env"

# Versões antigas guardavam estes arquivos na raiz do programa.
ARQUIVOS_DE_CONFIG = (".env", "listas.json")

MODELO_NOME_PADRAO = "{area}-{sobrenome}-{ano}-{titulo}"


@dataclass(frozen=True)
class Nivel:
    """Uma posição do controle "Esforço da IA" na janela."""
    nome: str
    familias: tuple       # famílias de modelo, na ordem de preferência
    paginas: int          # páginas iniciais enviadas
    raciocinio: str       # thinking_level do Gemini: MINIMAL, LOW, MEDIUM ou HIGH

    @property
    def descricao(self) -> str:
        return f"{self.familias[0]}, {self.paginas} páginas, raciocínio {RACIOCINIO[self.raciocinio]}"


RACIOCINIO = {"MINIMAL": "mínimo", "LOW": "baixo", "MEDIUM": "médio", "HIGH": "alto"}

# Se a família preferida estiver sem cota, o programa desce para a próxima da lista.
NIVEIS = [
    Nivel("Econômico", ("flash-lite", "flash"), 3, "MINIMAL"),
    Nivel("Normal", ("flash", "flash-lite"), 5, "LOW"),
    Nivel("Caprichado", ("flash", "flash-lite"), 10, "HIGH"),
    Nivel("Máximo", ("pro", "flash", "flash-lite"), 15, "HIGH"),
]
NIVEL_NORMAL = 1


@dataclass
class Config:
    api_key: str
    modelo: str
    rpm: int
    workers: int
    nivel: int
    modelo_nome: str
    python: str = ""   # vazio = o Iniciar.bat escolhe sozinho


def carregar() -> Config:
    """Uma variável de ambiente do sistema vence o que estiver escrito no config/.env."""
    migrar_da_raiz()
    arquivo = _ler_env(ARQUIVO_ENV)

    def ler(chave, padrao=""):
        return os.environ.get(chave) or arquivo.get(chave, padrao)

    return Config(
        api_key=ler("GEMINI_API_KEY"),
        modelo=ler("GEMINI_MODEL"),
        rpm=_inteiro(ler("GEMINI_RPM"), 10),
        workers=_inteiro(ler("GEMINI_WORKERS"), 4),
        nivel=_nivel(ler("NIVEL_IA")),
        modelo_nome=ler("MODELO_NOME") or MODELO_NOME_PADRAO,
        python=arquivo.get("PYTHON", ""),   # só do config/.env: é ele que o Iniciar.bat lê
    )


def salvar_chave(chave: str, caminho: Path | None = None) -> None:
    salvar_no_env("GEMINI_API_KEY", chave, caminho)


def salvar_no_env(nome: str, valor: str, caminho: Path | None = None) -> None:
    """
    Grava NOME=valor no config/.env, trocando só essa linha. As outras linhas e os
    comentários ficam como estão. Sem .env, parte do .env.example.
    """
    caminho = caminho or ARQUIVO_ENV
    caminho.parent.mkdir(parents=True, exist_ok=True)
    if caminho.exists():
        linhas = caminho.read_text(encoding="utf-8").splitlines()
    elif (exemplo := caminho.with_name(".env.example")).exists():
        linhas = exemplo.read_text(encoding="utf-8").splitlines()
    else:
        linhas = []
    nova = f"{nome}={valor.strip()}"
    for i, linha in enumerate(linhas):
        if linha.strip().startswith(f"{nome}="):
            linhas[i] = nova
            break
    else:
        linhas.insert(0, nova)
    caminho.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def migrar_da_raiz() -> None:
    """
    Move para config/ o .env e o listas.json deixados na raiz por versões antigas.
    Se já existir um em config/, o da raiz fica onde está (nada é sobrescrito).
    O Iniciar.bat faz o mesmo antes de abrir o programa.
    """
    for nome in ARQUIVOS_DE_CONFIG:
        antigo, novo = PASTA_DO_PROJETO / nome, PASTA_CONFIG / nome
        if antigo.is_file() and not novo.exists():
            PASTA_CONFIG.mkdir(parents=True, exist_ok=True)
            antigo.replace(novo)


def chave_mascarada(chave: str) -> str:
    """Mostra só o começo e o fim: dá para reconhecer a chave sem expô-la."""
    if not chave or chave == "cole_sua_chave_aqui":
        return "(nenhuma)"
    return f"{chave[:4]}…{chave[-4:]}" if len(chave) > 10 else "…"


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


def _nivel(valor) -> int:
    try:
        return min(max(int(valor), 0), len(NIVEIS) - 1)
    except (TypeError, ValueError):
        return NIVEL_NORMAL
