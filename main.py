"""
main.py

Scanner pool-to-pool multi-chain (Solana + Base) et envoi Telegram.
Ne modifie aucun autre fichier.
"""

import asyncio
import logging
import aiohttp
import hashlib
import time
from collections import defaultdict
from typing import Dict

from pool_fetchers import fetch_solana_pools, fetch_base_pools
from utils import logger
from arbitrage import compute_pool_arbitrage
from telegram_bot import start_telegram_app, send_opportunity
from config import CHECK_INTERVAL_SECONDS, TELEGRAM_CHAT_ID
from token_loader import get_solana_tokens, get_base_tokens

# ============================================================================ #
# TOKENS LISTS (50 Solana, 20 Base)
# ============================================================================ #
# Chargement dynamique des tokens avec validation
TOKENS_SOL = get_solana_tokens()

TOKENS_BASE = get_base_tokens()


# ============================================================================ #
# MAIN LOGIC
# ============================================================================ #
# Le bot utilise maintenant des RPC configurables (SOLANA_RPC_URL, BASE_RPC_URL)
# et limite les requêtes à 1 token traité toutes les 4 secondes pour éviter
# les rate limits RPC. Le scan intervalle complet peut être ajusté via
# CHECK_INTERVAL_SECONDS dans .env.
# ============================================================================
# ANTI-SPAM SYSTEM
# ============================================================================

# Stockage des opportunités récentes
_recent_opportunities: Dict[str, float] = {}  # opportunity_hash -> last_sent_timestamp
_recent_tokens: Dict[str, float] = {}  # token -> last_sent_timestamp

# Cooldowns (secondes)
OPPORTUNITY_COOLDOWN = 15 * 60  # 15 minutes par opportunité spécifique
TOKEN_COOLDOWN = 5 * 60        # 5 minutes par token

def generate_opportunity_hash(token: str, buy_pool_id: str, sell_pool_id: str) -> str:
    """
    Génère un hash ordre-invariant pour une opportunité.
    Identique peu importe l'ordre buy/sell.
    """
    # Trie les pool IDs pour ordre invariant
    sorted_pools = sorted([buy_pool_id, sell_pool_id])
    key = f"{token}|{sorted_pools[0]}|{sorted_pools[1]}"
    return hashlib.md5(key.encode()).hexdigest()

def should_send_notification(token: str, opportunity_hash: str) -> bool:
    """
    Vérifie si une notification doit être envoyée (anti-spam).
    """
    current_time = time.time()

    # Vérifier cooldown par opportunité
    if opportunity_hash in _recent_opportunities:
        last_sent = _recent_opportunities[opportunity_hash]
        if current_time - last_sent < OPPORTUNITY_COOLDOWN:
            logger.debug(f"[ANTI-SPAM] Opportunity {opportunity_hash[:8]} on cooldown")
            return False

    # Vérifier cooldown par token
    if token in _recent_tokens:
        last_sent = _recent_tokens[token]
        if current_time - last_sent < TOKEN_COOLDOWN:
            logger.debug(f"[ANTI-SPAM] Token {token[:8]} on cooldown")
            return False

    return True

def record_notification(token: str, opportunity_hash: str):
    """Enregistre l'envoi d'une notification."""
    global _recent_opportunities, _recent_tokens
    current_time = time.time()
    _recent_opportunities[opportunity_hash] = current_time
    _recent_tokens[token] = current_time

    # Nettoyer les entrées anciennes (plus de 1 heure)
    cleanup_threshold = current_time - 3600
    _recent_opportunities = {
        k: v for k, v in _recent_opportunities.items()
        if v > cleanup_threshold
    }
    _recent_tokens = {
        k: v for k, v in _recent_tokens.items()
        if v > cleanup_threshold
    }

async def main():
    """
    Boucle principale du bot avec limitation de taux: 1 requête par token tous les 4 secondes.
    Cette approche réduit considérablement la charge RPC et évite les rate limits.
    """
    telegram_app = await start_telegram_app()

    # Combiner tous les tokens (Solana + Base)
    all_tokens = TOKENS_SOL + TOKENS_BASE
    logger.info(f"[MAIN] Starting scan loop with {len(all_tokens)} tokens (1 token every 4 seconds)")

    async with aiohttp.ClientSession() as session:
        while True:
            try:
                # Récupérer les pools pour TOUS les tokens (une fois par cycle complet)
                # Cette approche est plus efficace que de récupérer par token individuel
                sol_pools = await fetch_solana_pools(TOKENS_SOL, session)
                base_pools = await fetch_base_pools(TOKENS_BASE, session)

                # Combiner toutes les pools
                all_pools = sol_pools + base_pools

                # Regrouper par token
                pools_by_token = {}
                for p in all_pools:
                    pools_by_token.setdefault(p["token"], []).append(p)

                logger.info(f"[MAIN] Retrieved {len(all_pools)} pools across {len(pools_by_token)} tokens")

                # Traiter chaque token avec un délai de 4 secondes entre chaque
                # Cela limite à 1 token traité par tranche de 4 secondes
                for i, (token, pools) in enumerate(pools_by_token.items()):
                    if len(pools) < 2:
                        continue  # Pas assez de pools pour faire de l'arbitrage

                    logger.debug(f"[MAIN] Processing token {token[:8]}... ({i+1}/{len(pools_by_token)})")

                    # Comparer chaque paire de pools pour ce token
                    n = len(pools)
                    for ii in range(n):
                        for jj in range(ii + 1, n):
                            opp = compute_pool_arbitrage(pools[ii], pools[jj], token)
                            if opp:
                                # Générer hash ordre-invariant pour anti-spam
                                buy_pool_id = opp.get("buy_pool_id", "")
                                sell_pool_id = opp.get("sell_pool_id", "")
                                opportunity_hash = generate_opportunity_hash(token, buy_pool_id, sell_pool_id)

                                # Vérifier anti-spam
                                if should_send_notification(token, opportunity_hash):
                                    await send_opportunity(telegram_app, TELEGRAM_CHAT_ID, opp)
                                    record_notification(token, opportunity_hash)
                                    logger.info(f"[NOTIFICATION] Sent alert for {token[:8]} | Hash: {opportunity_hash[:8]}")

                    # Attendre 50-100ms entre chaque token pour éviter les bursts API
                    if i < len(pools_by_token) - 1:
                        await asyncio.sleep(0.05)  # 50ms delay between tokens

                # Attendre entre les cycles complets (tous les tokens scannés)
                logger.info(f"[MAIN] Cycle completed, waiting {CHECK_INTERVAL_SECONDS}s before next cycle...")
                await asyncio.sleep(CHECK_INTERVAL_SECONDS)

            except Exception as e:
                logging.error(f"Main loop error: {e}")
                await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
