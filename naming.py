"""
Montagem dos nomes de arquivo.

Tudo aqui é função pura: recebe texto, devolve texto, sem tocar em disco nem em
rede (a única exceção é `caminho_livre`, que precisa olhar se o arquivo existe).
Isso facilita testar, e as regras de nome são justamente onde mais aparecem
casos estranhos.
"""

import re
import unicodedata
from pathlib import Path

# Caracteres que o Windows não aceita em nome de arquivo, mais os de controle.
PROIBIDOS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

# Nomes que o Windows reserva para dispositivos. Um arquivo "CON.pdf" não pode existir.
RESERVADOS = {"CON", "PRN", "AUX", "NUL",
              *(f"COM{i}" for i in range(1, 10)),
              *(f"LPT{i}" for i in range(1, 10))}

# O Windows limita o caminho inteiro a 260 caracteres. 150 para o nome deixa
# espaço para pastas razoavelmente fundas.
TAMANHO_MAXIMO = 150


def montar_nome(modelo: str, campos: dict) -> str:
    """
    Preenche um modelo como '{area}-{sobrenome}-{ano}-{titulo}'.

    Campos vazios somem junto com o separador. Sem ano, por exemplo, sai
    'Física-Souza-Título.pdf' e não 'Física-Souza--Título.pdf'.
    """
    valores = {chave: limpar_parte(valor) for chave, valor in campos.items()}
    valores["titulo"] = primeira_maiuscula(valores.get("titulo", ""))
    valores["sobrenome"] = primeira_maiuscula(valores.get("sobrenome", ""))

    pedacos = []
    for pedaco in re.split(r"(\{\w+\})", modelo):
        campo = re.fullmatch(r"\{(\w+)\}", pedaco)
        pedacos.append(valores.get(campo.group(1), "") if campo else pedaco)

    nome = "".join(pedacos)
    nome = re.sub(r"(\s*[-_]\s*){2,}", "-", nome)   # separadores encavalados
    return finalizar_nome(nome)


def finalizar_nome(nome: str) -> str:
    """Garante que o nome é aceito pelo Windows e termina em .pdf."""
    nome = nome.strip()
    if nome.lower().endswith(".pdf"):
        nome = nome[:-4]
    nome = limpar_parte(nome)[:TAMANHO_MAXIMO].rstrip(" .-")
    if not nome:
        nome = "Sem titulo"
    if nome.split(".")[0].upper() in RESERVADOS:
        nome = "_" + nome
    return nome + ".pdf"


def limpar_parte(texto) -> str:
    """Troca caracteres proibidos por espaço e arruma espaços sobrando."""
    if not texto:
        return ""
    # NFC junta "e" + "acento" num caractere só; senão nomes iguais parecem diferentes.
    texto = unicodedata.normalize("NFC", str(texto))
    texto = PROIBIDOS.sub(" ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto.strip(" .-")


def primeira_maiuscula(texto: str) -> str:
    """
    Sobe só a primeira letra. Diferente de str.capitalize(), não rebaixa o resto,
    então siglas (DNA, IBGE) e nomes próprios (Einstein) sobrevivem.
    """
    return texto[:1].upper() + texto[1:] if texto else texto


def caminho_livre(pasta: Path, nome: str, ja_usados: set | None = None) -> Path:
    """
    Devolve pasta/nome. Se já existir, tenta 'nome (2).pdf', 'nome (3).pdf'...

    `ja_usados` guarda os nomes escolhidos nesta mesma leva de cópias, para dois
    arquivos novos com o mesmo nome também não se atropelarem. A comparação
    ignora maiúsculas porque o Windows também ignora.
    """
    ja_usados = ja_usados if ja_usados is not None else set()
    base, extensao = Path(nome).stem, Path(nome).suffix
    candidato = pasta / nome
    numero = 2
    while candidato.exists() or str(candidato).lower() in ja_usados:
        candidato = pasta / f"{base} ({numero}){extensao}"
        numero += 1
    ja_usados.add(str(candidato).lower())
    return candidato
