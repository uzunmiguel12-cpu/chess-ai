@echo off
REM ---------------------------------------------------------------------------
REM  Riavvia il backend FastAPI di chess-ai (porta 8000).
REM  Ferma un eventuale uvicorn gia' in ascolto sulla 8000 e lo riavvia pulito,
REM  cosi' il profilo (caricato ALL'AVVIO) viene ricostruito con i dati nuovi.
REM
REM  Si lancia da qualunque cartella: si sposta da solo nella radice del progetto.
REM  Avvia SENZA --reload, di proposito: --reload a volte non ricarica i moduli ml/*.
REM  Il backend resta in questa finestra; premi Ctrl+C per fermarlo.
REM ---------------------------------------------------------------------------

setlocal
set PORT=8000

REM Vai nella radice del progetto (questo .bat vive in scripts\, quindi ..).
cd /d "%~dp0.."

echo [1/3] Cerco un processo in ascolto sulla porta %PORT% ...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr LISTENING ^| findstr :%PORT%') do (
    echo     Trovato PID %%p in ascolto: lo fermo con tutto l'albero.
    taskkill /F /T /PID %%p
)

REM Diamo tempo al sistema operativo di rilasciare davvero la porta prima di
REM ri-legarla: senza questa attesa il nuovo uvicorn puo' fallire con errore 10048
REM (la vecchia socket e' ancora "appesa" per un istante dopo la kill).
echo     Attendo il rilascio della porta %PORT% ...
timeout /t 3 /nobreak >nul

echo [2/3] Attivo la venv ed entro in api\ ...
call .venv\Scripts\activate.bat
cd api

echo [3/3] Avvio uvicorn sulla porta %PORT% (Ctrl+C per fermare) ...
uvicorn server:app --port %PORT%
