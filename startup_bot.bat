@echo off
REM ============================================================
REM   DEMARRAGE AUTOMATIQUE DU BOT D'ARBITRAGE
REM   Ce fichier doit etre copie dans le dossier Startup Windows
REM   (Win+R -> shell:startup)
REM ============================================================

REM Aller dans le dossier du projet (CHEMIN ABSOLU)
cd /d "C:\Users\oryew\OneDrive\Desktop\arb"

REM Lancer le bot principal
start "Solana Arbitrage Bot" cmd /k py main.py

REM Attendre 5 secondes
timeout /t 5 /nobreak >nul

REM Lancer l'API REST
start "Solana Arbitrage API" cmd /k py api.py

REM Message de confirmation
echo Bot et API lances avec succes!

