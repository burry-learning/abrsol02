#!/bin/bash
# Script pour lancer le bot en continu sur Linux/VPS
# Usage: ./run_forever.sh

set -e

# Obtenir le répertoire du script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "============================================================"
echo "  LANCEMENT DU BOT D'ARBITRAGE (VPS/Linux)"
echo "============================================================"
echo ""
echo "Répertoire: $SCRIPT_DIR"
echo ""

# Vérifier que Python est installé
if ! command -v python3 &> /dev/null; then
    echo "[ERREUR] Python3 non trouvé !"
    echo "Installe Python3: sudo apt install python3 python3-pip"
    exit 1
fi

# Vérifier que .env existe
if [ ! -f ".env" ]; then
    echo "[ATTENTION] Fichier .env non trouvé !"
    echo "Crée un fichier .env avec TELEGRAM_BOT_TOKEN et TELEGRAM_CHAT_ID"
    echo ""
fi

# Créer le dossier logs s'il n'existe pas
mkdir -p logs

# Fonction pour logger
log_with_timestamp() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a logs/bot_launcher.log
}

# Fonction pour redémarrer le bot
restart_bot() {
    log_with_timestamp "Redémarrage du bot..."
    pkill -f "python3 main.py" || true
    sleep 2
    nohup python3 main.py >> logs/bot_output.log 2>&1 &
    echo $! > logs/bot.pid
    log_with_timestamp "Bot redémarré (PID: $(cat logs/bot.pid))"
}

# Fonction pour arrêter le bot
stop_bot() {
    log_with_timestamp "Arrêt du bot..."
    if [ -f logs/bot.pid ]; then
        kill $(cat logs/bot.pid) 2>/dev/null || true
        rm logs/bot.pid
    fi
    pkill -f "python3 main.py" || true
    log_with_timestamp "Bot arrêté"
}

# Gérer les signaux
trap stop_bot SIGTERM SIGINT

# Lancer le bot en arrière-plan
log_with_timestamp "Lancement du bot..."
nohup python3 main.py >> logs/bot_output.log 2>&1 &
echo $! > logs/bot.pid
log_with_timestamp "Bot lancé (PID: $(cat logs/bot.pid))"

# Boucle de surveillance (redémarre si crash)
while true; do
    sleep 60  # Vérifier toutes les minutes
    
    # Vérifier si le processus tourne toujours
    if [ -f logs/bot.pid ]; then
        PID=$(cat logs/bot.pid)
        if ! ps -p $PID > /dev/null 2>&1; then
            log_with_timestamp "Bot crashé ! Redémarrage..."
            restart_bot
        fi
    else
        log_with_timestamp "Fichier PID perdu ! Redémarrage..."
        restart_bot
    fi
done

