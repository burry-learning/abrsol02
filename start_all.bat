@echo off
REM Script pour lancer le Bot + l'API en même temps
REM Double-cliquer sur ce fichier pour tout démarrer

echo ============================================================
echo   DEMARRAGE DU BOT D'ARBITRAGE SOLANA
echo ============================================================
echo.
echo Demarrage du bot principal...
echo.

cd /d "%~dp0"

REM Lancer le bot principal dans une nouvelle fenêtre
start "Solana Arbitrage Bot" cmd /k py main.py

REM Attendre 5 secondes que le bot démarre
timeout /t 5 /nobreak

echo.
echo Demarrage de l'API REST...
echo.

REM Lancer l'API dans une nouvelle fenêtre
start "Solana Arbitrage API" cmd /k py api.py

echo.
echo ============================================================
echo   BOT ET API LANCES !
echo ============================================================
echo.
echo Bot principal : http://localhost:8000
echo API REST      : http://localhost:8001/docs
echo.
echo NE PAS FERMER CES FENETRES !
echo.
echo Pour arreter : Fermer les 2 fenetres ou faire Ctrl+C
echo.
pause

