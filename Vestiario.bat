@echo off
rem Abre o Vestiário: sobe o servidor (numa janela minimizada) e o navegador. Se já estiver aberto, só abre o navegador.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente nao encontrado. Veja a instalacao no README.md.
  pause
  exit /b 1
)
if not exist "web\dist\index.html" (
  echo Gerando as telas pela primeira vez...
  pushd web && call npm run build && popd
)
start "Vestiario" /min ".venv\Scripts\python.exe" -m vestiario
