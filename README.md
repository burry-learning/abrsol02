 🚀 Bot d'Arbitrage Solana

Bot d'arbitrage inter-DEX sur Solana avec détection en temps réel et alertes Telegram.

## 📋 Table des matières

- [Démarrage rapide](#-démarrage-rapide)
- [Fonctionnalités](#-fonctionnalités)
- [Installation](#-installation)
- [Configuration](#-configuration)
- [Utilisation](#-utilisation)
- [API REST](#-api-rest)
- [Troubleshooting](#-troubleshooting)
- [Améliorations récentes](#-améliorations-récentes)


### En 3 étapes :

1. **Configuration** : Créer `.env` depuis `env.template`
2. **Installation** : `pip install -r requirements.txt`
3. **Lancement** : Double-cliquer sur `start_all.bat`

## ✨ Fonctionnalités

### Core
- 🔍 **Détection multi-DEX** : Compare les prix réels sur 6 DEX (Jupiter, Raydium, Orca, Meteora, PumpFun, OpenBook)
- 💰 **Calcul de spread net** : Inclut tous les frais (DEX, réseau, slippage, impact de prix)
- 📱 **Alertes Telegram** : Notifications instantanées avec détails complets
- 🎯 **Filtres intelligents** : Liquidité, volume, âge du pool, nombre de holders
- 🌐 **Interface Web** : Dashboard en temps réel avec statistiques
- 🔌 **API REST** : Endpoints pour intégration avec Lovable ou autres dashboards

### Sécurité
- ✅ Vérification de liquidité minimum
- ✅ Analyse du volume 24h
- ✅ Détection de variations de prix suspectes
- ✅ Protection contre les scams et tokens à faible liquidité
- ✅ Mode simulation (pas d'exécution automatique de trades)

## 🛠️ Installation

### Prérequis
- Python 3.9+ (recommandé: 3.11)
- pip
- Un bot Telegram (créé via @BotFather)

### Installation

#### 1. Installer les dépendances
```bash
pip install -r requirements.txt
```

#### 2. Configuration
```bash
# Copier le template de configuration
cp env.template .env

# Éditer le fichier .env avec vos credentials
nano .env  # ou votre éditeur préféré
```

**Variables obligatoires :**
```env
TELEGRAM_BOT_TOKEN=votre_token_ici
TELEGRAM_CHAT_ID=votre_chat_id_ici
```

**Comment obtenir ces valeurs ?**
- Token Telegram : Créer un bot via [@BotFather](https://t.me/BotFather) sur Telegram
- Chat ID : Envoyer un message à [@userinfobot](https://t.me/userinfobot) sur Telegram

## ⚙️ Configuration

### Configuration des tokens à surveiller

Par défaut, le bot surveille 10 tokens populaires :
- SOL, USDC, USDT, BONK, JUP, RAY, WIF, POPCAT, MEW, PYTH
- et 50autres sur sol , +20 sur base , bloqués actuellement .

Pour personnaliser, éditer `.env` :
```env
TOKENS=token1_address,token2_address,token3_address
```

### Ajuster les seuils

```env
# Spread minimum pour alerter (0.3% = 0.003)
MIN_SPREAD_AFTER_FEES=0.003

# Intervalle de scan (secondes)
CHECK_INTERVAL_SECONDS=4

# Liquidité minimum (USD)
MIN_LIQUIDITY_USD=50000

# Volume 24h minimum (USD)
MIN_VOLUME_24H=100000
```

## 🚀 Utilisation

### Lancer le bot

#### Windows (Double-clic)
```
start_all.bat
```

#### Ligne de commande
```bash
python main.py
```

Le bot va :
1. Démarrer l'interface web sur http://localhost:8000
2. Se connecter à Telegram
3. Commencer à scanner les tokens toutes les 60 secondes
4. Envoyer des alertes quand des opportunités sont détectées

### Arrêter le bot

```bash
# Ctrl+C si en mode foreground

# Windows
taskkill /F /IM python.exe
```

## 🌐 API REST

Le bot expose une API REST pour intégration avec des dashboards externes (Lovable, etc.).

### Lancer l'API

```bash
python api.py
```





### Endpoints principaux

| Endpoint | Description |
|----------|-------------|
| `GET /api/status` | Statut du bot (uptime, opportunités, etc.) |
| `GET /api/tokens` | Liste des tokens surveillés |
| `GET /api/dex` | Liste des DEX supportés |
| `GET /api/opportunities` | Historique des opportunités |
| `GET /api/prices/realtime` | Prix en temps réel par DEX |
| `GET /api/opportunities/stats` | Statistiques globales |



**Pour plus de détails, consultez la documentation Swagger :** http://localhost:8001/docs

## 🧪 Tests

### Tester la récupération de prix

```bash
python test_price_differences.py
```

**OU double-cliquer sur :**
```
test_bot.bat
```

### Tester Telegram

```bash
python scripts/test_telegram_connection.py
```

## 🐛 Troubleshooting

### Problème: "TELEGRAM_BOT_TOKEN not set"

```bash
# Windows PowerShell
Get-Content .env | Select-String TELEGRAM_BOT_TOKEN
```

### Problème: Pas d'opportunités détectées

**Causes possibles :**
1. Seuil trop élevé → Baisser `MIN_SPREAD_AFTER_FEES` à `0.001` (0.1%)
2. Marchés efficaces → C'est normal, les arbitrages sont rares
3. Tokens peu actifs → Ajouter des tokens plus populaires

**Solutions :**
```env
# Baisser le seuil pour plus d'opportunités
MIN_SPREAD_AFTER_FEES=0.001

# Vérifier plus souvent
CHECK_INTERVAL_SECONDS=30

# Ajouter plus de tokens
TOKENS=token1,token2,token3,...
```

### Problème: Erreurs SSL/HTTP

**Solution:** 
```bash
pip install --upgrade aiohttp certifi
```

### Problème: Rate limiting (429)

**Solution:** Augmenter `CHECK_INTERVAL_SECONDS` dans `.env` (ex: 120 secondes)

## 📈 Améliorations Récentes

### Version actuelle (Novembre 2025)

1. ✅ **Récupération de prix améliorée** : Récupère les vrais prix par DEX (pas agrégés)
2. ✅ **10 tokens par défaut** : Plus de chances de trouver des opportunités
3. ✅ **Seuil abaissé** : 0.3% au lieu de 0.5%
4. ✅ **Logs détaillés** : Voir exactement ce qui se passe
5. ✅ **API REST complète** : Endpoint `/api/prices/realtime` pour dashboards
6. ✅ **Script de test** : `test_price_differences.py` pour vérifier le fonctionnement

### Comment ça fonctionne maintenant

Le bot récupère les prix **directement depuis chaque DEX** via DexScreener :
- Parse toutes les paires Solana pour chaque token
- Extrait le prix spécifique de chaque DEX
- Compare les vraies différences de prix
- Détecte les opportunités d'arbitrage

**Résultat :** Le bot peut maintenant détecter des spreads réels entre les DEX !

## 📁 Structure du Projet

```
arb/
├── COMMENCER_ICI.md          # Guide de démarrage rapide
├── README.md                  # Documentation principale (ce fichier)
├── main.py                    # Bot principal
├── api.py                     # API REST
├── arbitrage.py               # Logique de détection
├── price_fetchers.py          # Récupération de prix par DEX
├── price_sources_aggregator.py # Agrégation multi-sources
├── telegram_bot.py            # Intégration Telegram
├── config.py                  # Configuration
├── utils.py                   # Utilitaires
├──               # Template de configuration
├── requirements.txt           # Dépendances
├── start_all.bat              # Lanceur Windows
├── test_bot.bat               # Test rapide
├── docs/                      # Documentation détaillée
│   └── (guides spécialisés)
├── scripts/                   # Scripts de test
│   ├── test_price_differences.py
│   └── test_telegram_connection.py
└── logs/                      # Fichiers de logs
```

## 🔒 Sécurité

### ⚠️ Règles Critiques


2. **Ne jamais partager** votre
3. **Utiliser des RPC privés** pour production (Helius, QuickNode)
4. **Toujours simuler** avant d'exécuter des trades
5. **Attention au MEV** et frontrunning

### Mode Simulation

Ce bot est en **mode simulation** :
- Détecte les opportunités
- Envoie des alertes
- **N'exécute PAS automatiquement** les trades

Pour exécuter des trades, vous devrez :
1. Ajouter un wallet Solana
2. Implémenter l'exécution automatique
3. Gérer la protection MEV (Jito)
4. Tester en mode devnet d'abord

## 📚 Documentation Complémentaire

- * - Guide de démarrage rapide
- **docs/** - Guides détaillés et diagnostics
- )

## 📝 Licence

Ce projet est fourni à des fins éducatives uniquement. Utilisez-le à vos propres risques.

**⚠️ DISCLAIMER:**
- Ce bot NE garantit AUCUN profit
- Le trading comporte des risques de perte en capital
- Toujours tester en mode simulation avant production
- Les marchés crypto sont volatils et imprévisibles
