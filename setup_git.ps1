# Script PowerShell pour configurer Git et pousser vers GitHub

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuration Git pour GitHub" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Vérifier si Git est installé
try {
    $gitVersion = git --version 2>&1
    Write-Host "[OK] Git trouvé: $gitVersion" -ForegroundColor Green
} catch {
    Write-Host "[ERREUR] Git n'est pas installé ou pas dans le PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Veuillez installer Git depuis: https://git-scm.com/download/win" -ForegroundColor Yellow
    Write-Host "Ou via winget: winget install Git.Git" -ForegroundColor Yellow
    exit 1
}

Write-Host ""

# Vérifier que .env est dans .gitignore
if (Test-Path .env) {
    Write-Host "[INFO] Fichier .env détecté" -ForegroundColor Yellow
    $gitignoreContent = Get-Content .gitignore -ErrorAction SilentlyContinue
    if ($gitignoreContent -match "^\.env$") {
        Write-Host "[OK] .env est bien dans .gitignore" -ForegroundColor Green
    } else {
        Write-Host "[ATTENTION] .env n'est pas dans .gitignore - ajout..." -ForegroundColor Yellow
        Add-Content .gitignore "`n.env"
        Write-Host "[OK] .env ajouté à .gitignore" -ForegroundColor Green
    }
} else {
    Write-Host "[INFO] Pas de fichier .env (normal si pas encore créé)" -ForegroundColor Gray
}

Write-Host ""

# Initialiser Git si pas déjà fait
if (-not (Test-Path .git)) {
    Write-Host "[INIT] Initialisation du dépôt Git..." -ForegroundColor Cyan
    git init
    if ($LASTEXITCODE -eq 0) {
        Write-Host "[OK] Dépôt Git initialisé" -ForegroundColor Green
    } else {
        Write-Host "[ERREUR] Échec de l'initialisation Git" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "[INFO] Dépôt Git déjà initialisé" -ForegroundColor Gray
}

Write-Host ""

# Vérifier les fichiers à committer
Write-Host "[VÉRIFICATION] Fichiers à committer..." -ForegroundColor Cyan
git status --short
Write-Host ""

# Vérifier que .env n'est pas dans les fichiers trackés
$trackedFiles = git ls-files 2>&1
if ($trackedFiles -match "\.env") {
    Write-Host "[ATTENTION] .env est tracké par Git! Retrait..." -ForegroundColor Red
    git rm --cached .env 2>&1 | Out-Null
    Write-Host "[OK] .env retiré du tracking" -ForegroundColor Green
    Write-Host ""
}

# Demander confirmation
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Voulez-vous continuer avec le commit initial?" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Les fichiers suivants seront commités:" -ForegroundColor Yellow
Write-Host "  - Tous les fichiers Python (.py)" -ForegroundColor Gray
Write-Host "  - Configuration (.gitignore, requirements.txt, etc.)" -ForegroundColor Gray
Write-Host "  - Documentation (README.md, etc.)" -ForegroundColor Gray
Write-Host ""
Write-Host "Les fichiers suivants seront IGNORÉS:" -ForegroundColor Yellow
Write-Host "  - .env (contient les tokens secrets)" -ForegroundColor Gray
Write-Host "  - __pycache__/ (fichiers Python compilés)" -ForegroundColor Gray
Write-Host "  - logs/ (fichiers de logs)" -ForegroundColor Gray
Write-Host "  - .venv/ (environnement virtuel)" -ForegroundColor Gray
Write-Host ""

$confirm = Read-Host "Continuer? (O/N)"
if ($confirm -ne "O" -and $confirm -ne "o") {
    Write-Host "Opération annulée" -ForegroundColor Yellow
    exit 0
}

# Ajouter tous les fichiers (sauf ceux dans .gitignore)
Write-Host ""
Write-Host "[ADD] Ajout des fichiers..." -ForegroundColor Cyan
git add .
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Fichiers ajoutés" -ForegroundColor Green
} else {
    Write-Host "[ERREUR] Échec de l'ajout des fichiers" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Commit initial
Write-Host "[COMMIT] Création du commit initial..." -ForegroundColor Cyan
git commit -m "Initial commit: Bot d'arbitrage Solana/Base"
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Commit créé" -ForegroundColor Green
} else {
    Write-Host "[ATTENTION] Aucun changement à committer (peut-être déjà commité?)" -ForegroundColor Yellow
}

Write-Host ""

# Vérifier la branche
Write-Host "[BRANCH] Vérification de la branche..." -ForegroundColor Cyan
$currentBranch = git branch --show-current
Write-Host "Branche actuelle: $currentBranch" -ForegroundColor Gray
Write-Host ""

# Ajouter le remote
Write-Host "[REMOTE] Configuration du remote GitHub..." -ForegroundColor Cyan
git remote remove origin 2>&1 | Out-Null
git remote add origin https://github.com/burry-learning/solarbv01.git
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Remote ajouté" -ForegroundColor Green
} else {
    Write-Host "[ERREUR] Échec de l'ajout du remote" -ForegroundColor Red
    exit 1
}

Write-Host ""

# Renommer la branche en main si nécessaire
Write-Host "[BRANCH] Renommage de la branche en 'main'..." -ForegroundColor Cyan
git branch -M main
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] Branche renommée en 'main'" -ForegroundColor Green
} else {
    Write-Host "[ATTENTION] Impossible de renommer la branche (peut-être déjà 'main'?)" -ForegroundColor Yellow
}

Write-Host ""

# Afficher les instructions finales
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Configuration terminée!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Pour pousser vers GitHub, exécutez:" -ForegroundColor Yellow
Write-Host "  git push -u origin main" -ForegroundColor White
Write-Host ""
Write-Host "OU si vous êtes déjà authentifié, je peux le faire maintenant..." -ForegroundColor Gray
Write-Host ""

$push = Read-Host "Pousser maintenant vers GitHub? (O/N)"
if ($push -eq "O" -or $push -eq "o") {
    Write-Host ""
    Write-Host "[PUSH] Envoi vers GitHub..." -ForegroundColor Cyan
    git push -u origin main
    if ($LASTEXITCODE -eq 0) {
        Write-Host ""
        Write-Host "[SUCCESS] Projet poussé vers GitHub avec succès!" -ForegroundColor Green
        Write-Host "URL: https://github.com/burry-learning/solarbv01" -ForegroundColor Cyan
    } else {
        Write-Host ""
        Write-Host "[ERREUR] Échec du push. Vérifiez:" -ForegroundColor Red
        Write-Host "  - Votre authentification GitHub (token ou SSH)" -ForegroundColor Yellow
        Write-Host "  - Les permissions sur le dépôt" -ForegroundColor Yellow
        Write-Host "  - Votre connexion internet" -ForegroundColor Yellow
        Write-Host ""
        Write-Host "Vous pouvez réessayer plus tard avec: git push -u origin main" -ForegroundColor Gray
    }
} else {
    Write-Host ""
    Write-Host "Vous pouvez pousser plus tard avec: git push -u origin main" -ForegroundColor Gray
}

Write-Host ""

