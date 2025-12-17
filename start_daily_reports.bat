@echo off
REM Script pour lancer les rapports quotidiens automatiques
REM Lance le bot + les rapports quotidiens à 9h00
REM VERSION CORRIGEE pour démarrage automatique Windows

chcp 65001 > nul
setlocal enabledelayedexpansion

REM Obtenir le répertoire ABSOLU du script (important pour démarrage auto)
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Chercher Python avec chemin complet
set PYTHON_CMD=
where py >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_CMD=py
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% == 0 (
        set PYTHON_CMD=python
    ) else (
        if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe" (
            set PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe
        ) else (
            set PYTHON_CMD=python
        )
    )
)

echo ============================================================
echo   DEMARRAGE BOT + RAPPORTS QUOTIDIENS
echo ============================================================
echo.
echo Repertoire: %SCRIPT_DIR%
echo Python: %PYTHON_CMD%
echo.
echo Ce script va lancer:
echo   1. Le bot d'arbitrage principal
echo   2. L'API REST
echo   3. Les rapports quotidiens (9h00 chaque jour)
echo.
echo NE PAS FERMER CES FENETRES !
echo.
echo ============================================================
echo.

REM Lancer le bot principal (avec chemin complet)
start "Arbitrage Bot" cmd /k "cd /d %SCRIPT_DIR% && %PYTHON_CMD% main.py"

REM Attendre 5 secondes
timeout /t 5 /nobreak >nul

REM Lancer l'API (avec chemin complet)
start "API REST" cmd /k "cd /d %SCRIPT_DIR% && %PYTHON_CMD% api.py"

REM Attendre 3 secondes
timeout /t 3 /nobreak >nul

REM Lancer les rapports quotidiens (avec chemin complet)
start "Rapports Quotidiens 9h00" cmd /k "cd /d %SCRIPT_DIR% && %PYTHON_CMD% daily_price_report.py"

echo.
echo ============================================================
echo   3 SERVICES LANCES !
echo ============================================================
echo.
echo 1. Bot d'arbitrage    : http://localhost:8000
echo 2. API REST           : http://localhost:8001/docs
echo 3. Rapports quotidiens: Tous les jours a 9h00 Paris
echo.
echo Pour arreter : Fermer les 3 fenetres
echo.
pause

