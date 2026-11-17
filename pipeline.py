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

from google.genai import errors

from cache import Cache
from config import NIVEIS
from gemini_client import Cancelado, ClienteGemini, descrever_erro
from pdf_tools import InfoPDF, hash_arquivo, ler_pdf
from schema import MetadadosPDF

# Situações possíveis de cada arquivo depois de analisado.
OK, CACHE, BAIXA, ERRO = "ok", "cache", "baixa", "erro"

# Abaixo disto, a linha fica amarela e a cópia vai para a pasta .verificar.
LIMIAR_CONFIANCA = 0.6


@dataclass
class Resultado:
    caminho: Path
    status: str
    dados: MetadadosPDF | None = None
    info: InfoPDF | None = None
    erro: str = ""
    modelo: str = ""
    nivel: int = 0
    repetir: bool = True   # False quando insistir não adianta (PDF ilegível, chave errada)


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

    def __init__(self, cliente: ClienteGemini, cache: Cache, nivel: int, workers: int,
                 fila: Queue | None = None, geracao: int = 0, escalar: bool = True):
        self.cliente = cliente
        self.cache = cache
        self.nivel = nivel
        self.escalar = escalar
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
            resultado = analisar_um(caminho, self.cliente, self.cache, self.nivel,
                                    self.cancelado, self.instrucoes.get(caminho, ""),
                                    self.usar_cache, self.escalar)
        except Cancelado:
            return
        except Exception as erro:
            # Uma thread que morre calada deixa a linha presa em ⏳ para sempre.
            resultado = Resultado(caminho, ERRO, erro=descrever_erro(erro))
        self._emitir("resultado", resultado)

    def _emitir(self, tipo, carga):
        self.fila.put((self.geracao, tipo, carga))


def analisar_um(caminho: Path, cliente: ClienteGemini, cache: Cache, nivel: int,
                cancelado: threading.Event, instrucao: str = "",
                usar_cache: bool = True, escalar: bool = False) -> Resultado:
    """
    O caminho completo de um único PDF:
    hash -> cache? -> lê o PDF -> Gemini -> (dúvida? nível seguinte) -> cache.

    Com `escalar`, um resultado com erro ou confiança baixa é refeito uma vez no
    nível seguinte, e fica o melhor dos dois.

    O cache é consultado antes de abrir o PDF de propósito: calcular o hash é
    bem mais rápido do que extrair texto e páginas.
    """
    sha = hash_arquivo(caminho)
    niveis = [nivel]
    if escalar and nivel + 1 < len(NIVEIS):
        niveis.append(nivel + 1)

    melhor = None
    if usar_cache and not instrucao:
        guardado = cache.obter(sha)
        if guardado and guardado.nivel >= nivel:
            melhor = Resultado(caminho, CACHE, guardado.dados, modelo=guardado.modelo,
                               nivel=guardado.nivel)
            if guardado.dados.confianca < LIMIAR_CONFIANCA:
                melhor.status = BAIXA
            # Só volta ao Gemini se ficou em dúvida e ainda há um nível acima para tentar.
            niveis = [n for n in niveis if n > guardado.nivel] if melhor.status == BAIXA else []
            if not niveis:
                return melhor

    tentado = nivel
    for n in niveis:
        resultado = _analisar_no_nivel(caminho, sha, n, cliente, cancelado, instrucao)
        if resultado.dados:   # falha de cota não conta como nível tentado
            tentado = n
        melhor = _o_melhor(melhor, resultado)
        if resultado.status == OK or not resultado.repetir:
            break

    if melhor.dados and melhor.status != CACHE:
        # O nível anotado é o mais alto já tentado, para não repetir a escalada à toa.
        cache.salvar(sha, melhor.modelo, melhor.dados, max(tentado, melhor.nivel))
    return melhor


def _analisar_no_nivel(caminho, sha, n, cliente, cancelado, instrucao) -> Resultado:
    info = ler_pdf(caminho, NIVEIS[n].paginas, sha)
    if info.erro:
        return Resultado(caminho, ERRO, info=info, erro=info.erro, nivel=n, repetir=False)
    try:
        dados, modelo = cliente.analisar(info, instrucao, cancelado, NIVEIS[n])
    except Cancelado:
        raise
    except Exception as erro:
        definitivo = isinstance(erro, errors.ClientError) and erro.code in (401, 403)
        return Resultado(caminho, ERRO, info=info, erro=descrever_erro(erro), nivel=n,
                         repetir=not definitivo)
    status = BAIXA if dados.confianca < LIMIAR_CONFIANCA else OK
    return Resultado(caminho, status, dados, info, modelo=modelo, nivel=n)


def _o_melhor(a: Resultado | None, b: Resultado) -> Resultado:
    """Com dados vence sem dados; entre dois com dados, vence a maior confiança."""
    if a is None or not a.dados:
        return b if (b.dados or a is None) else a
    if not b.dados:
        return a
    return b if b.dados.confianca >= a.dados.confianca else a
