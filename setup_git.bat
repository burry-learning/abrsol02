@echo off
REM Script pour initialiser Git et pousser vers GitHub
echo ========================================
echo Configuration Git pour GitHub
echo ========================================
echo.

REM Vérifier si Git est installé
where git >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERREUR] Git n'est pas installe ou pas dans le PATH
    echo.
    echo Veuillez installer Git depuis: https://git-scm.com/download/win
    echo Ou ajouter Git au PATH systeme
    pause
    exit /b 1
)

echo [OK] Git trouve
echo.

REM Vérifier si .env existe et est bien ignoré
if exist .env (
    echo [INFO] Fichier .env detecte
    echo [VERIFICATION] .env doit etre dans .gitignore
    findstr /C:".env" .gitignore >nul 2>&1
    if %ERRORLEVEL% EQU 0 (
        echo [OK] .env est bien dans .gitignore
    ) else (
        echo [ATTENTION] .env n'est pas dans .gitignore - ajout...
        echo .env >> .gitignore
    )
) else (
    echo [INFO] Pas de fichier .env (normal si pas encore cree)
)
echo.

REM Initialiser Git si pas déjà fait
if not exist .git (
    echo [INIT] Initialisation du depot Git...
    git init
    echo [OK] Depot Git initialise
) else (
    echo [INFO] Depot Git deja initialise
)
echo.

REM Vérifier les fichiers à committer
echo [VERIFICATION] Fichiers a committer...
git status --short
echo.

REM Demander confirmation
echo ========================================
echo Voulez-vous continuer avec le commit initial?
echo ========================================
echo.
echo Les fichiers suivants seront commits:
echo - Tous les fichiers Python (.py)
echo - Configuration (.gitignore, requirements.txt, etc.)
echo - Documentation (README.md, etc.)
echo.
echo Les fichiers suivants seront IGNORES:
echo - .env (contient les tokens secrets)
echo - __pycache__/ (fichiers Python compiles)
echo - logs/ (fichiers de logs)
echo - .venv/ (environnement virtuel)
echo.
set /p confirm="Continuer? (O/N): "
if /i not "%confirm%"=="O" (
    echo Operation annulee
    pause
    exit /b 0
)

REM Ajouter tous les fichiers (sauf ceux dans .gitignore)
echo.
echo [ADD] Ajout des fichiers...
git add .
echo [OK] Fichiers ajoutes
echo.

REM Commit initial
echo [COMMIT] Creation du commit initial...
git commit -m "Initial commit: Bot d'arbitrage Solana/Base"
if %ERRORLEVEL% NEQ 0 (
    echo [ATTENTION] Aucun changement a committer (peut-etre deja commit?)
) else (
    echo [OK] Commit cree
)
echo.

REM Vérifier la branche
echo [BRANCH] Verification de la branche...
git branch
echo.

REM Ajouter le remote
echo [REMOTE] Ajout du remote GitHub...
git remote remove origin 2>nul
git remote add origin https://github.com/burry-learning/solarbv01.git
echo [OK] Remote ajoute
echo.

REM Renommer la branche en main si nécessaire
echo [BRANCH] Renommage de la branche en 'main'...
git branch -M main
echo [OK] Branche renommee en 'main'
echo.

REM Afficher les instructions finales
echo ========================================
echo Configuration terminee!
echo ========================================
echo.
echo Pour pousser vers GitHub, executez:
echo   git push -u origin main
echo.
echo OU si vous etes deja authentifie, je peux le faire maintenant...
echo.
set /p push="Pousser maintenant vers GitHub? (O/N): "
if /i "%push%"=="O" (
    echo.
    echo [PUSH] Envoi vers GitHub...
    git push -u origin main
    if %ERRORLEVEL% EQU 0 (
        echo.
        echo [SUCCESS] Projet pousse vers GitHub avec succes!
        echo URL: https://github.com/burry-learning/solarbv01
    ) else (
        echo.
        echo [ERREUR] Echec du push. Verifiez:
        echo - Votre authentification GitHub (token ou SSH)
        echo - Les permissions sur le depot
        echo - Votre connexion internet
    )
) else (
    echo.
    echo Vous pouvez pousser plus tard avec: git push -u origin main
)
echo.
pause

