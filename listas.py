"""
As listas de categorias e de áreas que a pessoa pode editar.

Ficam em config/listas.json, dentro da pasta do programa. Sem esse arquivo, valem as listas
que vêm com o programa (schema.CATEGORIAS_PADRAO e schema.AREAS_PADRAO).

Categoria vira nome de subpasta na cópia e é uma lista fechada para a IA.
Área é só sugestão: a IA pode responder outra, e a pessoa pode digitar outra
na tabela.
"""

import json
from dataclasses import dataclass, field

import config
from schema import AREAS_PADRAO, CATEGORIAS_PADRAO, OUTROS

ARQUIVO = config.PASTA_CONFIG / "listas.json"


@dataclass
class Listas:
    categorias: list[str] = field(default_factory=lambda: list(CATEGORIAS_PADRAO))
    areas: list[str] = field(default_factory=lambda: list(AREAS_PADRAO))


def limpar(itens, com_outros: bool = False) -> list[str]:
    """Tira espaços sobrando, linhas vazias e repetidos (sem ligar para maiúsculas)."""
    vistos, resultado = set(), []
    for item in itens:
        item = " ".join(str(item).split())
        if item and item.casefold() not in vistos:
            vistos.add(item.casefold())
            resultado.append(item)
    if com_outros and OUTROS.casefold() not in vistos:
        resultado.append(OUTROS)   # a categoria de reserva nunca some
    return resultado


def carregar(arquivo=ARQUIVO) -> Listas:
    """Arquivo ausente ou estragado: volta para as listas padrão, sem quebrar."""
    try:
        bruto = json.loads(arquivo.read_text(encoding="utf-8"))
        return Listas(limpar(bruto.get("categorias") or CATEGORIAS_PADRAO, com_outros=True),
                      limpar(bruto.get("areas") or AREAS_PADRAO))
    except (OSError, ValueError, AttributeError):
        return Listas()


def salvar(listas: Listas, arquivo=ARQUIVO) -> None:
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    conteudo = {"categorias": limpar(listas.categorias, com_outros=True),
                "areas": limpar(listas.areas)}
    arquivo.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
