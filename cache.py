"""
Memória das análises já feitas.

Cada análise custa uma chamada ao Gemini (tempo e cota). Guardamos o resultado
num SQLite indexado pelo hash do conteúdo do PDF, não pelo nome: assim, mesmo
que o arquivo seja renomeado ou movido, ele continua sendo reconhecido.

Também fica anotado até que nível de esforço o arquivo já foi analisado. Uma
análise feita no Econômico não serve para quem pediu Caprichado.
"""

import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

from schema import MetadadosPDF


@dataclass
class Guardado:
    dados: MetadadosPDF
    modelo: str
    nivel: int


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
            " criado_em TEXT DEFAULT CURRENT_TIMESTAMP,"
            " nivel INTEGER DEFAULT 1)"
        )
        # Caches criados antes dos níveis não têm a coluna; entram como Normal.
        colunas = [c[1] for c in self._conexao.execute("PRAGMA table_info(analises)")]
        if "nivel" not in colunas:
            self._conexao.execute("ALTER TABLE analises ADD COLUMN nivel INTEGER DEFAULT 1")
        self._conexao.commit()

    def obter(self, sha256: str) -> Guardado | None:
        with self._trava:
            linha = self._conexao.execute(
                "SELECT dados, modelo, nivel FROM analises WHERE sha256 = ?",
                (sha256,)).fetchone()
        if not linha:
            return None
        try:
            return Guardado(MetadadosPDF.model_validate_json(linha[0]), linha[1] or "",
                            linha[2] if linha[2] is not None else 1)
        except ValueError:
            # Guardado por uma versão antiga, com outro formato. Melhor reanalisar.
            return None

    def salvar(self, sha256: str, modelo: str, dados: MetadadosPDF, nivel: int = 1) -> None:
        with self._trava:
            self._conexao.execute(
                "INSERT OR REPLACE INTO analises (sha256, modelo, dados, nivel)"
                " VALUES (?, ?, ?, ?)",
                (sha256, modelo, dados.model_dump_json(), nivel))
            self._conexao.commit()
