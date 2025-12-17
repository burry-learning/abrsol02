# daily_price_report.py
"""
Module pour envoyer des rapports quotidiens des prix à 9h00 Paris.

Fonctionnalités:
- Envoie un rapport quotidien avec tous les prix des tokens surveillés
- Récupère les prix depuis les DEX natifs uniquement
- Envoie le rapport via Telegram
- Fonctionne en boucle infinie (attente jusqu'à 9h00 chaque jour)
"""
import asyncio
import aiohttp
from datetime import datetime, time, timedelta
from typing import Dict, List
from config import TELEGRAM_CHAT_ID
from utils import logger
from telegram_bot import start_telegram_app
from price_fetchers import get_all_dex_prices
from base_dex_fetchers import get_all_base_dex_prices, USDC_BASE

# Gestion du fuseau horaire Paris (UTC+1 ou UTC+2 selon l'heure d'été)
try:
    import pytz
    PARIS_TZ = pytz.timezone("Europe/Paris")
    HAS_PYTZ = True
except ImportError:
    # Fallback sans pytz: utiliser UTC+1 (approximation, ne gère pas l'heure d'été)
    PARIS_TZ = None
    HAS_PYTZ = False

# Tokens surveillés (même liste que dans main.py)
TOKENS_SOLANA = [
    "So11111111111111111111111111111111111111112",  # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",   # JUP
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",   # PYTH
]

TOKENS_BASE = [
    "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b",  # VIRTUAL
    "0x532f27101965dd16442e59d40670faf5ebb142e4",  # BRETT
    "0xac1bd2486aaf3b5c0fc3fd868558b082a531b2b4",  # TOSHI
]

BASE_TOKEN_SOLANA = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC


def wait_until_9am_paris() -> float:
    """
    Attend jusqu'à 9h00 Paris (timezone Europe/Paris).
    Si c'est déjà après 9h00, attend jusqu'à 9h00 le lendemain.
    """
    if HAS_PYTZ:
        now_paris = datetime.now(PARIS_TZ)
        target_time = now_paris.replace(hour=9, minute=0, second=0, microsecond=0)
        if now_paris >= target_time:
            target_time = target_time + timedelta(days=1)
        wait_seconds = (target_time - now_paris).total_seconds()
        logger.info(
            f"⏰ Prochain rapport à 9h00 Paris: {target_time.strftime('%d/%m/%Y %H:%M:%S')} "
            f"({int(wait_seconds / 3600)}h {int((wait_seconds % 3600) / 60)}m)"
        )
        return wait_seconds
    else:
        # Fallback sans pytz: UTC+1 (approximation)
        now_utc = datetime.utcnow()
        now_paris = now_utc + timedelta(hours=1)  # UTC+1
        target_time = now_paris.replace(hour=9, minute=0, second=0, microsecond=0)
        if now_paris >= target_time:
            target_time = target_time + timedelta(days=1)
        wait_seconds = (target_time - now_paris).total_seconds()
        logger.info(
            f"⏰ Prochain rapport à 9h00 Paris (approx UTC+1): {target_time.strftime('%d/%m/%Y %H:%M:%S')} "
            f"({int(wait_seconds / 3600)}h {int((wait_seconds % 3600) / 60)}m)"
        )
        return wait_seconds


async def fetch_solana_prices(session: aiohttp.ClientSession) -> Dict[str, Dict[str, float]]:
    """Récupère les prix de tous les tokens Solana depuis les DEX natifs."""
    prices = {}
    
    for token in TOKENS_SOLANA:
        try:
            dex_prices = await get_all_dex_prices(session, token, BASE_TOKEN_SOLANA)
            if dex_prices:
                prices[token] = dex_prices
        except Exception as e:
            logger.error(f"Erreur récupération prix Solana {token[:8]}...: {e}")
    
    return prices


async def fetch_base_prices(session: aiohttp.ClientSession) -> Dict[str, Dict[str, float]]:
    """Récupère les prix de tous les tokens Base depuis les DEX natifs."""
    prices = {}
    
    for token in TOKENS_BASE:
        try:
            dex_prices = await get_all_base_dex_prices(session, token, USDC_BASE)
            if dex_prices:
                prices[token] = dex_prices
        except Exception as e:
            logger.error(f"Erreur récupération prix Base {token[:8]}...: {e}")
    
    return prices


def format_price_report(
    solana_prices: Dict[str, Dict[str, float]],
    base_prices: Dict[str, Dict[str, float]],
    timestamp: datetime
) -> str:
    """Formate le rapport des prix pour Telegram."""
    lines = []
    
    # En-tête
    lines.append("📊 *RAPPORT QUOTIDIEN DES PRIX*")
    lines.append("")
    lines.append(f"🕐 Heure Paris: {timestamp.strftime('%d/%m/%Y à %H:%M:%S')}")
    lines.append(f"📅 Date: {timestamp.strftime('%A %d %B %Y')}")
    lines.append("")
    
    # Section Solana
    if solana_prices:
        lines.append("⛓️ *BLOCKCHAIN SOLANA*")
        lines.append("")
        
        token_names = {
            "So11111111111111111111111111111111111111112": "SOL",
            "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v": "USDC",
            "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
            "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "JUP",
            "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "PYTH",
        }
        
        for token, dex_prices in solana_prices.items():
            token_name = token_names.get(token, token[:8])
            lines.append(f"• *{token_name}*")
            
            # Trier les prix par DEX
            sorted_dex = sorted(dex_prices.items(), key=lambda x: x[1])
            for dex, price in sorted_dex:
                lines.append(f"  {dex.upper()}: ${price:.6f}")
            
            lines.append("")
    
    # Section Base
    if base_prices:
        lines.append("🔵 *BLOCKCHAIN BASE*")
        lines.append("")
        
        token_names = {
            "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b": "VIRTUAL",
            "0x532f27101965dd16442e59d40670faf5ebb142e4": "BRETT",
            "0xac1bd2486aaf3b5c0fc3fd868558b082a531b2b4": "TOSHI",
        }
        
        for token, dex_prices in base_prices.items():
            token_name = token_names.get(token, token[:8])
            lines.append(f"• *{token_name}*")
            
            # Trier les prix par DEX
            sorted_dex = sorted(dex_prices.items(), key=lambda x: x[1])
            for dex, price in sorted_dex:
                lines.append(f"  {dex.upper()}: ${price:.6f}")
            
            lines.append("")
    
    lines.append("_💡 Prix en USDC depuis les DEX natifs_")
    lines.append("_🔄 Prochain rapport: Demain à 9h00 Paris_")
    
    return "\n".join(lines)


async def send_daily_report(app, chat_id: int) -> None:
    """Récupère les prix et envoie le rapport quotidien."""
    if HAS_PYTZ:
        timestamp = datetime.now(PARIS_TZ)
    else:
        # Fallback sans pytz
        timestamp = datetime.utcnow() + timedelta(hours=1)
    
    logger.info("📊 Début génération rapport quotidien...")
    
    async with aiohttp.ClientSession() as session:
        # Récupérer les prix
        solana_prices = await fetch_solana_prices(session)
        base_prices = await fetch_base_prices(session)
        
        # Formater et envoyer
        report = format_price_report(solana_prices, base_prices, timestamp)
        
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=report,
                parse_mode="Markdown"
            )
            logger.info("✅ Rapport quotidien envoyé avec succès")
        except Exception as e:
            logger.error(f"❌ Erreur envoi rapport: {e}")


async def daily_report_loop() -> None:
    """
    Boucle principale pour les rapports quotidiens.
    Attend jusqu'à 9h00 Paris, envoie le rapport, puis attend jusqu'au lendemain.
    """
    logger.info("🕐 Module rapports quotidiens démarré (9h00 Paris chaque jour)")
    
    # Démarrer le bot Telegram
    app = await start_telegram_app()
    
    if not app or not TELEGRAM_CHAT_ID:
        logger.error("❌ Telegram non configuré, impossible d'envoyer les rapports")
        return
    
    # Boucle infinie
    while True:
        try:
            # Attendre jusqu'à 9h00 Paris
            wait_seconds = wait_until_9am_paris()
            await asyncio.sleep(wait_seconds)
            
            # Envoyer le rapport
            await send_daily_report(app, TELEGRAM_CHAT_ID)
            
            # Attendre 5 minutes avant de recalculer pour éviter les envois multiples
            await asyncio.sleep(300)
            
        except Exception as e:
            logger.exception(f"Erreur dans la boucle de rapports quotidiens: {e}")
            # Attendre 1 heure avant de réessayer en cas d'erreur
            await asyncio.sleep(3600)


if __name__ == "__main__":
    # Permet de lancer le script indépendamment
    asyncio.run(daily_report_loop())

