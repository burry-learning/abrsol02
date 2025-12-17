# Configuration Git pour GitHub

## Prérequis

1. **Installer Git** (si pas déjà installé)
   - Télécharger depuis: https://git-scm.com/download/win
   - Ou via winget: `winget install Git.Git`

2. **Vérifier l'installation**
   ```powershell
   git --version
   ```

## Instructions rapides

### Option 1: Utiliser le script automatique (recommandé)

```batch
setup_git.bat
```

Le script va:
- ✅ Vérifier que Git est installé
- ✅ Vérifier que `.env` est dans `.gitignore`
- ✅ Initialiser le dépôt Git si nécessaire
- ✅ Créer le commit initial
- ✅ Configurer le remote GitHub
- ✅ Renommer la branche en `main`
- ✅ Optionnellement pousser vers GitHub

### Option 2: Commandes manuelles

```bash
# 1. Initialiser Git (si pas déjà fait)
git init

# 2. Vérifier que .env est ignoré
# (déjà dans .gitignore, mais vérifiez)

# 3. Ajouter tous les fichiers
git add .

# 4. Créer le commit initial
git commit -m "Initial commit: Bot d'arbitrage Solana/Base"

# 5. Ajouter le remote GitHub
git remote add origin https://github.com/burry-learning/solarbv01.git

# 6. Renommer la branche en main
git branch -M main

# 7. Pousser vers GitHub
git push -u origin main
```

## Authentification GitHub

Si `git push` demande une authentification, vous avez 2 options:

### Option A: Token personnel (recommandé)

1. Créer un token sur GitHub:
   - Settings → Developer settings → Personal access tokens → Tokens (classic)
   - Générer un nouveau token avec les permissions `repo`

2. Utiliser le token comme mot de passe lors du push

### Option B: SSH (pour usage fréquent)

1. Générer une clé SSH:
   ```bash
   ssh-keygen -t ed25519 -C "votre_email@example.com"
   ```

2. Ajouter la clé publique à GitHub:
   - Settings → SSH and GPG keys → New SSH key

3. Changer l'URL du remote:
   ```bash
   git remote set-url origin git@github.com:burry-learning/solarbv01.git
   ```

## Fichiers ignorés (sécurité)

Les fichiers suivants sont automatiquement ignorés par Git:
- ✅ `.env` - Contient les tokens secrets (TELEGRAM_BOT_TOKEN, etc.)
- ✅ `__pycache__/` - Fichiers Python compilés
- ✅ `logs/` - Fichiers de logs
- ✅ `.venv/` - Environnement virtuel Python
- ✅ `*.log` - Tous les fichiers de logs

**⚠️ IMPORTANT**: Ne jamais committer `.env` ou tout fichier contenant des secrets!

## Vérification avant push

Avant de pousser, vérifiez:

```bash
# Voir ce qui sera commité
git status

# Voir les fichiers ignorés
git status --ignored

# Vérifier que .env n'est pas dans le commit
git ls-files | findstr .env
# (ne doit rien retourner)
```

## Commandes utiles

```bash
# Voir l'historique des commits
git log --oneline

# Voir les remotes configurés
git remote -v

# Changer l'URL du remote
git remote set-url origin https://github.com/burry-learning/solarbv01.git

# Mettre à jour depuis GitHub
git pull origin main

# Voir les différences
git diff
```

## Dépannage

### Erreur: "fatal: not a git repository"
```bash
git init
```

### Erreur: "remote origin already exists"
```bash
git remote remove origin
git remote add origin https://github.com/burry-learning/solarbv01.git
```

### Erreur: "authentication failed"
- Vérifiez votre token GitHub
- Ou configurez SSH (voir Option B ci-dessus)

### Erreur: "permission denied"
- Vérifiez que vous avez les droits d'écriture sur le dépôt
- Contactez le propriétaire du dépôt si nécessaire

