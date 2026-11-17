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
from datetime import datetime
from pathlib import Path

from naming import caminho_livre, finalizar_nome, limpar_parte

PASTA_VERIFICAR = ".verificar"


def copiar(itens: list[tuple[Path, str, str, bool]], destino: Path) -> dict:
    """
    Copia cada (arquivo_original, categoria, novo_nome, verificar) para
    destino/categoria/, ou destino/.verificar/categoria/ quando verificar=True.

    Devolve {"copiados": [...], "erros": [...], "log": caminho_do_log}.
    Um erro num arquivo não interrompe os outros.
    """
    ja_usados: set = set()
    copiados, erros = [], []

    for original, categoria, novo_nome, verificar in itens:
        try:
            base = destino / PASTA_VERIFICAR if verificar else destino
            pasta = base / (limpar_parte(categoria) or "Outros")
            pasta.mkdir(parents=True, exist_ok=True)
            alvo = caminho_livre(pasta, finalizar_nome(novo_nome), ja_usados)
            shutil.copy2(original, alvo)   # copy2 preserva a data original do arquivo
            copiados.append({"origem": str(original), "destino": str(alvo),
                             "verificar": verificar})
        except Exception as erro:
            erros.append({"origem": str(original), "erro": str(erro)})

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
