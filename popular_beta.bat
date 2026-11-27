@echo off
rem Preenche o banco BETA (local) com moradores ficticios. Nao toca no Supabase.
cd /d "%~dp0"
set ENV_FILE=.env.beta
set PORTARIA_BETA=1
".venv\Scripts\python.exe" popular_beta.py
pause
