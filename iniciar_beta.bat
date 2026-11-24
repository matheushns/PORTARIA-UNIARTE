@echo off
rem Abre o Portaria UNIARTE em modo BETA (banco local data\portaria_beta.db, sem atualizacao automatica).
cd /d "%~dp0"
set ENV_FILE=.env.beta
set PORTARIA_BETA=1
".venv\Scripts\python.exe" desktop.py
