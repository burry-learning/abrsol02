@echo off
REM Script pour lancer le bot en 1 clic sur Windows
REM Utilise le chemin complet de Python pour éviter les problèmes de PATH

chcp 65001 > nul
setlocal enabledelayedexpansion

REM Obtenir le répertoire du script
set SCRIPT_DIR=%~dp0
cd /d "%SCRIPT_DIR%"

REM Chercher Python (essayer plusieurs chemins possibles)
set PYTHON_CMD=
where py >nul 2>&1
if %ERRORLEVEL% == 0 (
    set PYTHON_CMD=py
) else (
    where python >nul 2>&1
    if %ERRORLEVEL% == 0 (
        set PYTHON_CMD=python
    ) else (
        REM Essayer les chemins communs
        if exist "C:\Python313\python.exe" (
            set PYTHON_CMD=C:\Python313\python.exe
        ) else if exist "C:\Python312\python.exe" (
            set PYTHON_CMD=C:\Python312\python.exe
        ) else if exist "C:\Python311\python.exe" (
            set PYTHON_CMD=C:\Python311\python.exe
        ) else if exist "C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe" (
            set PYTHON_CMD=C:\Users\%USERNAME%\AppData\Local\Programs\Python\Python313\python.exe
        ) else (
            echo [ERREUR] Python non trouve !
            echo Installe Python ou ajoute-le au PATH
            pause
            exit /b 1
        )
    )
)

echo ============================================================
echo   LANCEMENT DU BOT D'ARBITRAGE
echo ============================================================
echo.
echo Repertoire: %SCRIPT_DIR%
echo Python: %PYTHON_CMD%
echo.

REM Vérifier que .env existe
if not exist ".env" (
    echo [ATTENTION] Fichier .env non trouve !
    echo Cree un fichier .env avec TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID
    echo.
)

REM Lancer le bot (dans une fenêtre qui reste ouverte)
start "Bot Arbitrage Solana" cmd /k "%PYTHON_CMD%" main.py

echo.
echo ============================================================
echo   BOT LANCE !
echo ============================================================
echo.
echo La fenetre "Bot Arbitrage Solana" est ouverte.
echo NE PAS FERMER cette fenetre pour que le bot continue.
echo.
echo Pour arreter: Fermer la fenetre ou Ctrl+C
echo.
pause

