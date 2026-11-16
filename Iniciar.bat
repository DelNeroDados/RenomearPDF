@echo off
rem ==================================================================
rem  RenomearPDF - inicializador para Windows
rem
rem  De dois cliques neste arquivo. Ele:
rem    1. encontra o Python;
rem    2. instala as bibliotecas que faltarem (so na primeira vez);
rem    3. cria o arquivo .env e abre o Bloco de Notas para a chave;
rem    4. abre o programa.
rem
rem  "Iniciar.bat --testar" faz as verificacoes sem abrir a janela.
rem ==================================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title RenomearPDF

rem ---------- 1. Python ----------
rem Ordem: Python portatil do monorepo (se existir), lancador "py", "python".
set "PY="
if exist "%~dp0..\.python_embed\python.exe" set "PY="%~dp0..\.python_embed\python.exe""
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python >nul 2>nul && set "PY=python"
)
if not defined PY goto :sem_python

rem O "python" da Microsoft Store pode ser so um atalho vazio; testamos de verdade.
%PY% -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if errorlevel 1 goto :sem_python
echo [ok] Python encontrado.

rem ---------- 2. Bibliotecas ----------
%PY% -c "import google.genai, pypdf" >nul 2>nul
if errorlevel 1 (
    echo Instalando as bibliotecas, so acontece na primeira vez...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [erro] Nao foi possivel instalar as bibliotecas. Veja a mensagem acima.
        pause
        exit /b 1
    )
)
echo [ok] Bibliotecas instaladas.

rem ---------- 3. Chave da API ----------
if not exist ".env" (
    copy ".env.example" ".env" >nul
    echo.
    echo Primeira vez por aqui: crie sua chave em https://aistudio.google.com/apikey
    echo O Bloco de Notas vai abrir. Cole a chave depois de GEMINI_API_KEY=, salve e feche.
    echo.
    pause
    notepad ".env"
)
findstr /r /c:"^GEMINI_API_KEY=cole_sua_chave_aqui" ".env" >nul && (
    echo [aviso] A chave no .env ainda e a de exemplo. O programa vai abrir, mas a analise vai falhar.
)
echo [ok] Arquivo .env presente.

if /i "%~1"=="--testar" (
    echo.
    echo Tudo certo. Rode sem --testar para abrir o programa.
    exit /b 0
)

rem ---------- 4. Programa ----------
echo Abrindo o RenomearPDF...
%PY% Renomeador.py
if errorlevel 1 (
    echo.
    echo [erro] O programa fechou com erro. Veja a mensagem acima.
    pause
)
exit /b 0

:sem_python
echo.
echo [erro] Nao encontrei o Python 3.10 ou mais novo, com Tkinter.
echo Instale em https://www.python.org/downloads/ e marque "Add python.exe to PATH".
echo.
pause
exit /b 1
