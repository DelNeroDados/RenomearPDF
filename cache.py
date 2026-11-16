"""
Memória das análises já feitas.

Cada análise custa uma chamada ao Gemini (tempo e cota). Guardamos o resultado
num SQLite indexado pelo hash do conteúdo do PDF, não pelo nome: assim, mesmo
que o arquivo seja renomeado ou movido, ele continua sendo reconhecido.
"""

import sqlite3
import threading
from pathlib import Path

from schema import MetadadosPDF


class Cache:
    def __init__(self, caminho: Path):
        caminho.parent.mkdir(parents=True, exist_ok=True)
        # Várias threads usam a mesma conexão; a trava garante uma de cada vez.
        self._trava = threading.Lock()
        self._conexao = sqlite3.connect(str(caminho), check_same_thread=False)
        self._conexao.execute(
            "CREATE TABLE IF NOT EXISTS analises ("
            " sha256 TEXT PRIMARY KEY,"
            " modelo TEXT,"
            " dados TEXT,"
            " criado_em TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._conexao.commit()

    def obter(self, sha256: str) -> MetadadosPDF | None:
        with self._trava:
            linha = self._conexao.execute(
                "SELECT dados FROM analises WHERE sha256 = ?", (sha256,)).fetchone()
        if not linha:
            return None
        try:
            return MetadadosPDF.model_validate_json(linha[0])
        except ValueError:
            # Guardado por uma versão antiga, com outro formato. Melhor reanalisar.
            return None

    def salvar(self, sha256: str, modelo: str, dados: MetadadosPDF) -> None:
        with self._trava:
            self._conexao.execute(
                "INSERT OR REPLACE INTO analises (sha256, modelo, dados) VALUES (?, ?, ?)",
                (sha256, modelo, dados.model_dump_json()))
            self._conexao.commit()
