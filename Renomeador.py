"""
Renomeador de PDFs acadêmicos com Gemini. É por aqui que o programa começa.

    python Renomeador.py
"""

import os
import sys

# O Python portátil (embeddable) não coloca a pasta do script no caminho de
# importação. Sem esta linha, "import gui" falha.
PASTA = os.path.dirname(os.path.abspath(__file__))
if PASTA not in sys.path:
    sys.path.insert(0, PASTA)

from gui import main  # noqa: E402  (precisa vir depois do ajuste acima)

if __name__ == "__main__":
    main()
