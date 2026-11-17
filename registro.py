"""
O diário do programa: logs/renomearpdf.log, dentro da pasta do programa.

Guarda o que aconteceu em cada sessão (pasta analisada, resultado de cada
arquivo, cancelamentos, cópia) e qualquer erro inesperado, com o traceback.
Sem isto, um erro dentro da janela só aparecia no terminal e se perdia.

O arquivo é rotativo: passa de 1 MB, vira renomearpdf.log.1, e assim até 3
arquivos antigos. Nada de chave da API vai para cá.
"""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

import config

PASTA_LOGS = config.PASTA_DO_PROJETO / "logs"
ARQUIVO_LOG = PASTA_LOGS / "renomearpdf.log"

log = logging.getLogger("renomearpdf")


def iniciar() -> logging.Logger:
    """Liga o arquivo de log e passa a registrar os erros não tratados."""
    if log.handlers:
        return log   # já iniciado
    PASTA_LOGS.mkdir(parents=True, exist_ok=True)
    arquivo = RotatingFileHandler(ARQUIVO_LOG, maxBytes=1_000_000, backupCount=3,
                                  encoding="utf-8")
    arquivo.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                                           "%Y-%m-%d %H:%M:%S"))
    log.addHandler(arquivo)
    log.setLevel(logging.INFO)

    padrao_sys, padrao_thread = sys.excepthook, threading.excepthook

    def erro_geral(tipo, valor, tb):
        log.critical("Erro não tratado", exc_info=(tipo, valor, tb))
        padrao_sys(tipo, valor, tb)

    def erro_em_thread(args):
        nome = args.thread.name if args.thread else "?"
        log.critical("Erro não tratado na thread %s", nome,
                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))
        padrao_thread(args)

    sys.excepthook = erro_geral
    threading.excepthook = erro_em_thread
    return log
