"""
O meio de campo entre a janela e o Gemini.

A janela do Tkinter só pode ser mexida pela thread principal, e uma análise leva
segundos. Por isso o trabalho pesado roda aqui, em threads separadas, e cada
resultado é posto numa fila. A janela passa recolhendo essa fila de tempos em
tempos e se atualiza sozinha. Assim ela nunca congela.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from queue import Queue

from cache import Cache
from gemini_client import Cancelado, ClienteGemini, descrever_erro
from pdf_tools import InfoPDF, hash_arquivo, ler_pdf
from schema import MetadadosPDF

# Situações possíveis de cada arquivo depois de analisado.
OK, CACHE, BAIXA, ERRO = "ok", "cache", "baixa", "erro"

# Abaixo disto, a linha fica amarela pedindo revisão.
LIMIAR_CONFIANCA = 0.6


@dataclass
class Resultado:
    caminho: Path
    status: str
    dados: MetadadosPDF | None = None
    info: InfoPDF | None = None
    erro: str = ""


class Processador:
    """
    Analisa uma lista de PDFs em paralelo, em segundo plano.

    Cada evento sai na fila como (geracao, tipo, carga):
      - tipo "resultado": carga é um Resultado
      - tipo "aviso":     carga é um texto para a barra de status
      - tipo "fim":       acabou (carga diz se foi cancelado)

    A `geracao` é um número da rodada. Se o usuário cancelar e começar outra,
    a janela sabe ignorar os avisos que ainda chegarem da rodada velha.
    """

    def __init__(self, cliente: ClienteGemini, cache: Cache, paginas: int, workers: int,
                 fila: Queue | None = None, geracao: int = 0):
        self.cliente = cliente
        self.cache = cache
        self.paginas = paginas
        self.workers = workers
        self.fila = fila if fila is not None else Queue()
        self.geracao = geracao
        self.cancelado = threading.Event()
        self.instrucoes: dict = {}
        self.usar_cache = True
        cliente.ao_aviso = lambda mensagem: self._emitir("aviso", mensagem)

    def iniciar(self, caminhos: list[Path], instrucoes: dict | None = None,
                forcar: bool = False) -> None:
        """Começa em segundo plano e volta na hora. forcar=True ignora o cache."""
        self.instrucoes = instrucoes or {}
        self.usar_cache = not forcar
        self.cancelado.clear()
        threading.Thread(target=self._rodar, args=(caminhos,), daemon=True).start()

    def cancelar(self) -> None:
        self.cancelado.set()

    def _rodar(self, caminhos):
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(self._analisar_um_e_avisar, caminhos))
        self._emitir("fim", self.cancelado.is_set())

    def _analisar_um_e_avisar(self, caminho: Path) -> None:
        if self.cancelado.is_set():
            return
        try:
            resultado = analisar_um(caminho, self.cliente, self.cache, self.paginas,
                                    self.cancelado, self.instrucoes.get(caminho, ""),
                                    self.usar_cache)
        except Cancelado:
            return
        except Exception as erro:
            # Uma thread que morre calada deixa a linha presa em ⏳ para sempre.
            resultado = Resultado(caminho, ERRO, erro=descrever_erro(erro))
        self._emitir("resultado", resultado)

    def _emitir(self, tipo, carga):
        self.fila.put((self.geracao, tipo, carga))


def analisar_um(caminho: Path, cliente: ClienteGemini, cache: Cache, paginas: int,
                cancelado: threading.Event, instrucao: str = "",
                usar_cache: bool = True) -> Resultado:
    """
    O caminho completo de um único PDF:
    hash -> cache? -> lê o PDF -> Gemini -> guarda no cache.

    O cache é consultado antes de abrir o PDF de propósito: calcular o hash é
    bem mais rápido do que extrair texto e páginas.
    """
    sha = hash_arquivo(caminho)

    if usar_cache and not instrucao:
        guardado = cache.obter(sha)
        if guardado:
            return Resultado(caminho, CACHE, guardado)

    info = ler_pdf(caminho, paginas, sha)
    if info.erro:
        return Resultado(caminho, ERRO, info=info, erro=info.erro)

    try:
        dados = cliente.analisar(info, instrucao, cancelado)
    except Cancelado:
        raise
    except Exception as erro:
        return Resultado(caminho, ERRO, info=info, erro=descrever_erro(erro))

    cache.salvar(sha, cliente.modelo, dados)
    status = BAIXA if dados.confianca < LIMIAR_CONFIANCA else OK
    return Resultado(caminho, status, dados, info)
