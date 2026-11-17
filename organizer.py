"""
A cópia final para a pasta de saída.

Regra de ouro deste arquivo: os originais são sagrados. Só usamos cópia
(nunca mover ou renomear no lugar) e nunca sobrescrevemos nada. Se der algo
errado, o pior que acontece é sobrar uma cópia a mais.

Tudo é copiado. O que a IA não conseguiu ler, ou leu com pouca confiança, vai
para a pasta .verificar, separado do resto, esperando uma conferência.
"""

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from naming import caminho_livre, finalizar_nome, limpar_parte

PASTA_VERIFICAR = ".verificar"


@dataclass
class ItemCopia:
    original: Path
    categoria: str
    nome: str
    verificar: bool = False
    convertido: Path | None = None   # PDF gerado de um e-book; o original vai junto


def copiar(itens: list[ItemCopia], destino: Path) -> dict:
    """
    Copia cada item para destino/categoria/, ou destino/.verificar/categoria/.

    Um e-book convertido gera duas cópias com o mesmo nome: o PDF e o original
    (ex.: "Física-Souza-2020-Título.pdf" e "Física-Souza-2020-Título.epub").

    Devolve {"copiados": [...], "erros": [...], "log": caminho_do_log}.
    Um erro num arquivo não interrompe os outros.
    """
    ja_usados: set = set()
    copiados, erros = [], []

    for item in itens:
        try:
            base = destino / PASTA_VERIFICAR if item.verificar else destino
            pasta = base / (limpar_parte(item.categoria) or "Outros")
            pasta.mkdir(parents=True, exist_ok=True)
            registro = {"origem": str(item.original), "verificar": item.verificar}
            if item.convertido:
                alvo = caminho_livre(pasta, finalizar_nome(item.nome), ja_usados)
                shutil.copy2(item.convertido, alvo)
                # O original leva o mesmo nome (inclusive o "(2)", se houver).
                par = caminho_livre(pasta, alvo.stem + item.original.suffix.lower(), ja_usados)
                shutil.copy2(item.original, par)   # copy2 preserva a data original
                registro.update(destino=str(alvo), original_copiado_em=str(par))
            else:
                extensao = item.original.suffix.lower()
                alvo = caminho_livre(pasta, finalizar_nome(item.nome, extensao), ja_usados)
                shutil.copy2(item.original, alvo)
                registro["destino"] = str(alvo)
            copiados.append(registro)
        except Exception as erro:
            erros.append({"origem": str(item.original), "erro": str(erro)})

    log = _gravar_log(destino, copiados, erros) if (copiados or erros) else None
    return {"copiados": copiados, "erros": erros, "log": log}


def _gravar_log(destino: Path, copiados: list, erros: list) -> Path:
    """Deixa registrado de onde veio e para onde foi cada arquivo."""
    pasta_logs = destino / "_logs"
    pasta_logs.mkdir(parents=True, exist_ok=True)
    log = pasta_logs / f"copia_{datetime.now():%Y%m%d_%H%M%S}.json"
    conteudo = {"copiados": copiados, "erros": erros}
    log.write_text(json.dumps(conteudo, ensure_ascii=False, indent=2), encoding="utf-8")
    return log
