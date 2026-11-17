@echo off
rem ==================================================================
rem  RenomearPDF - inicializador para Windows
rem
rem  De dois cliques neste arquivo. Ele:
rem    1. encontra o Python (ou pergunta onde ele esta);
rem    2. instala as bibliotecas que faltarem (so na primeira vez);
rem    3. cria o arquivo config\.env e abre o Bloco de Notas para a chave;
rem    4. abre o programa.
rem
rem  "Iniciar.bat --testar" faz as verificacoes sem abrir a janela.
rem ==================================================================
setlocal
rem Sem chcp 65001 de proposito: com ele, o set /p (a pergunta pelo Python) perde
rem caminhos com acento. As mensagens daqui sao sem acento, e o Python escreve no
rem console por conta propria, sem depender da pagina de codigo.
cd /d "%~dp0"
title RenomearPDF

rem Configuracoes da pessoa ficam em config\. Versoes antigas deixavam na raiz.
if not exist "config" mkdir "config"
if exist ".env" if not exist "config\.env" move ".env" "config\.env" >nul
if exist "listas.json" if not exist "config\listas.json" move "listas.json" "config\listas.json" >nul

rem ---------- 1. Python ----------
rem Ordem: o escolhido em Configuracoes > Python (linha PYTHON= do config\.env);
rem o portatil do monorepo; o lancador "py"; as pastas onde o instalador do
rem python.org costuma por o Python; o "python" do PATH. Se nenhum servir,
rem pergunta onde esta o python.exe e guarda a resposta.
set "PY="
set "PY_ESCOLHIDO="
set "SALVAR_PY="
if exist "config\.env" for /f "usebackq tokens=1,* delims==" %%a in ("config\.env") do if /i "%%a"=="PYTHON" set "PY_ESCOLHIDO=%%b"
if not defined PY_ESCOLHIDO goto :python_automatico
if exist "%PY_ESCOLHIDO%" set "PY="%PY_ESCOLHIDO%"" & goto :python_testar
echo [aviso] O Python escolhido nas Configuracoes nao existe mais:
echo         %PY_ESCOLHIDO%
echo         Usando a escolha automatica.
:python_automatico
if exist "%~dp0..\.python_embed\python.exe" set "PY="%~dp0..\.python_embed\python.exe""
if not defined PY where py <nul >nul 2>nul && set "PY=py -3"
if not defined PY for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "PY="%%d\python.exe""
if not defined PY for /d %%d in ("%ProgramFiles%\Python3*") do if exist "%%d\python.exe" set "PY="%%d\python.exe""
if not defined PY where python <nul >nul 2>nul && set "PY=python"
if not defined PY goto :sem_python

:python_testar
rem O "python" da Microsoft Store pode ser so um atalho vazio; testamos de verdade.
%PY% -c "import sys, tkinter; sys.exit(0 if sys.version_info >= (3, 10) else 1)" <nul >nul 2>nul
if errorlevel 1 goto :python_nao_serve
echo [ok] Python encontrado: %PY%

rem ---------- 2. Bibliotecas ----------
rem Importa tudo o que o programa usa direto e confere a versao do google-genai:
rem um Python emprestado de outro projeto pode ter as bibliotecas pela metade.
%PY% -c "import google.genai, httpx, pydantic, pypdf, pymupdf; from importlib.metadata import version as v; assert tuple(int(n) for n in v('google-genai').split('.')[:2]) >= (2, 17)" <nul >nul 2>nul
if errorlevel 1 (
    echo Instalando as bibliotecas, so acontece na primeira vez...
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [erro] Nao foi possivel instalar as bibliotecas. Veja a mensagem acima.
        echo Se a mensagem disser "No module named pip", esse Python nao tem o pip:
        echo use outro Python ou instale o pip nele.
        pause
        exit /b 1
    )
)
echo [ok] Bibliotecas instaladas.

rem ---------- 3. Chave da API ----------
if not exist "config\.env" (
    copy "config\.env.example" "config\.env" >nul
    echo.
    echo Primeira vez por aqui: crie sua chave em https://aistudio.google.com/apikey
    echo O Bloco de Notas vai abrir. Cole a chave depois de GEMINI_API_KEY=, salve e feche.
    echo.
    pause
    notepad "config\.env"
)
findstr /r /c:"^GEMINI_API_KEY=cole_sua_chave_aqui" "config\.env" >nul && (
    echo [aviso] A chave no config\.env ainda e a de exemplo. O programa vai abrir, mas a analise vai falhar.
)
echo [ok] Arquivo config\.env presente.

rem O Python que a pessoa indicou fica guardado; da proxima vez nao pergunta.
rem Quem grava e o proprio Python, pelo config.py, que troca so a linha PYTHON=.
if defined SALVAR_PY %PY% -c "import sys; sys.path.insert(0, '.'); import config; config.salvar_no_env('PYTHON', sys.argv[1])" "%PY_ESCOLHIDO%"
if defined SALVAR_PY echo [ok] Python guardado em config\.env.

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

:python_nao_serve
echo.
echo [erro] O Python %PY% nao serve: precisa ser 3.10 ou mais novo, com Tkinter.
goto :perguntar_python

:sem_python
echo.
echo [erro] Nao encontrei o Python 3.10 ou mais novo, com Tkinter.

:perguntar_python
if /i "%~1"=="--testar" exit /b 1
echo.
echo Se o Python ja esta neste computador (portatil ou instalado), mostre onde
echo fica o python.exe: cole o caminho completo ou arraste o arquivo para esta
echo janela e aperte Enter. So Enter abre uma janela para procurar.
echo Para instalar: https://www.python.org/downloads/ (marque "Add python.exe to PATH").
echo.
set "PY_ESCOLHIDO="
set /p "PY_ESCOLHIDO=Caminho do python.exe (Enter = procurar, S = sair): "
rem Arrastar o arquivo para a janela traz aspas; tiramos.
if defined PY_ESCOLHIDO set "PY_ESCOLHIDO=%PY_ESCOLHIDO:"=%"
if /i "%PY_ESCOLHIDO%"=="S" exit /b 1
if not defined PY_ESCOLHIDO for /f "usebackq delims=" %%f in (`powershell -NoProfile -STA -Command "Add-Type -AssemblyName System.Windows.Forms; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Title = 'Escolha o python.exe'; $d.Filter = 'python.exe|python.exe|Programas (*.exe)|*.exe'; if ($d.ShowDialog() -eq 'OK') { $d.FileName }"`) do set "PY_ESCOLHIDO=%%f"
if not defined PY_ESCOLHIDO goto :perguntar_python
if not exist "%PY_ESCOLHIDO%" echo [erro] Arquivo nao encontrado: %PY_ESCOLHIDO% & goto :perguntar_python
set "PY="%PY_ESCOLHIDO%""
set "SALVAR_PY=1"
goto :python_testar
