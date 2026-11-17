"""
Encontra e testa os Pythons do computador, para o menu Configurações → Python…

Quem escolhe o Python de verdade é o Iniciar.bat, antes de a janela abrir. O
programa só grava a escolha na linha PYTHON= do config/.env; vazio é "automático"
(o portátil, se existir; senão, o instalado).
"""

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import config

PORTATIL = config.PASTA_DO_PROJETO.parent / ".python_embed" / "python.exe"

# Uma janela preta piscando a cada teste assusta; no Windows, rodamos sem ela.
SEM_JANELA = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_TESTE = r"""
import sys
print(sys.version.split()[0])
try:
    import tkinter
    print("tk ok")
except Exception:
    print("tk falta")
faltando = []
for nome in ("google.genai", "pypdf", "pymupdf"):
    try:
        __import__(nome)
    except Exception:
        faltando.append(nome.split(".")[-1])
print("faltando:" + ",".join(faltando))
"""


@dataclass
class Teste:
    ok: bool
    versao: str = ""
    faltando: tuple = ()
    erro: str = ""


def candidatos() -> list[Path]:
    """O portátil primeiro, depois os instalados. Sem repetidos."""
    achados = []
    if PORTATIL.exists():
        achados.append(PORTATIL)
    achados += _do_lancador_py()
    for raiz in (os.environ.get("LOCALAPPDATA", "") + r"\Programs\Python",
                 os.environ.get("ProgramFiles", r"C:\Program Files")):
        if raiz and Path(raiz).is_dir():
            achados += sorted(Path(raiz).glob("Python3*/python.exe"), reverse=True)
    for nome in ("python", "python3"):
        if caminho := shutil.which(nome):
            achados.append(Path(caminho))

    vistos, resultado = set(), []
    for exe in achados:
        chave = str(exe.resolve()).casefold()
        # O "python.exe" da pasta WindowsApps é só um atalho para a Microsoft Store.
        if chave in vistos or "windowsapps" in chave:
            continue
        vistos.add(chave)
        resultado.append(exe)
    return resultado


def _do_lancador_py() -> list[Path]:
    """O lançador "py" sabe onde estão os Pythons instalados pelo python.org."""
    if not shutil.which("py"):
        return []
    try:
        saida = subprocess.run(["py", "-0p"], capture_output=True, text=True, timeout=10,
                               creationflags=SEM_JANELA).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return [Path(m) for m in re.findall(r"([A-Za-z]:\\.+?python\.exe)", saida)]


def em_uso() -> Path:
    return Path(sys.executable)


def testar(exe: Path) -> Teste:
    """Roda o Python escolhido e confere versão, Tkinter e bibliotecas."""
    if not exe.is_file():
        return Teste(False, erro="arquivo não encontrado")
    try:
        r = subprocess.run([str(exe), "-c", _TESTE], capture_output=True, text=True,
                           timeout=30, creationflags=SEM_JANELA)
    except (OSError, subprocess.SubprocessError) as erro:
        return Teste(False, erro=str(erro))
    linhas = r.stdout.split()
    if r.returncode != 0 or len(linhas) < 3:
        return Teste(False, erro=(r.stderr.strip().splitlines() or ["não respondeu"])[-1])

    versao = linhas[0]
    faltando = tuple(f for f in linhas[-1].removeprefix("faltando:").split(",") if f)
    numeros = tuple(int(n) for n in re.findall(r"\d+", versao)[:2])
    if numeros < (3, 10):
        return Teste(False, versao, faltando, f"Python {versao} é antigo; precisa do 3.10 ou mais novo")
    if "tk ok" not in r.stdout:
        return Teste(False, versao, faltando, "sem Tkinter, que desenha a janela")
    return Teste(True, versao, faltando)
