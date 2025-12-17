# telegram_bot.py
"""
Module de gestion du bot Telegram avec commandes interactives.

Commandes disponibles:
- /start : Démarrer le bot et voir le menu
- /status : Voir le statut du bot
- /tokensuivies : Liste des tokens surveillés
- /dex : Liste des DEX supportés
- /perf : Historique des arbitrages détectés
- /help : Aide et commandes disponibles
"""
import asyncio
import os
from datetime import datetime
from typing import Optional, List, Dict
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, ContextTypes
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from utils import logger, format_percentage, truncate_address

# Store global pour l'historique des opportunités
opportunities_history: List[Dict] = []

# Informations sur les tokens suivis (Solana + Base)
TRACKED_TOKENS_SOLANA = {
    "pumpCmXqMfrsAkQ5r49WcJnRayYRqmXz6ae8H7H9Dfn": "PUMP",
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263": "BONK",
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN": "Jupiter (JUP)",
    "3iQL8BFS2vE7mww4ehAqQHAsbmRNCrPxizWAT2Zfyr9y": "Virtual (SOL)",
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3": "Pyth"
}

TRACKED_TOKENS_BASE = {
    "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b": "Virtual (BASE)",
    "0x940181a94A35A4569E4529A3CDfB74e38FD98631": "AERO",
    "0xc0634090F2Fe6c6d75e61Be2b949464aBB498973": "KTA"
}

# Tous les tokens combinés (pour backward compatibility)
TRACKED_TOKENS = {**TRACKED_TOKENS_SOLANA, **TRACKED_TOKENS_BASE}

# Solana DEX (6)
SUPPORTED_DEX_SOLANA = {
    "jupiter": {"name": "Jupiter", "fee": "0.1%", "type": "Aggregator", "chain": "Solana"},
    "raydium": {"name": "Raydium", "fee": "0.25%", "type": "AMM", "chain": "Solana"},
    "orca": {"name": "Orca", "fee": "0.3%", "type": "Whirlpools", "chain": "Solana"},
    "meteora": {"name": "Meteora", "fee": "0.2%", "type": "DLMM", "chain": "Solana"},
    "phoenix": {"name": "Phoenix", "fee": "0.02%", "type": "Order Book", "chain": "Solana"},
    "lifinity": {"name": "Lifinity", "fee": "0.2%", "type": "PMM", "chain": "Solana"},
}

# Base DEX (3)
SUPPORTED_DEX_BASE = {
    "uniswap": {"name": "Uniswap V3", "fee": "0.3%", "type": "AMM", "chain": "Base"},
    "aerodrome": {"name": "Aerodrome", "fee": "0.2%", "type": "AMM", "chain": "Base"},
    "baseswap": {"name": "BaseSwap", "fee": "0.3%", "type": "AMM", "chain": "Base"},
}

# Tous les DEX combinés
SUPPORTED_DEX = {**SUPPORTED_DEX_SOLANA, **SUPPORTED_DEX_BASE}

# ============================================================================
# COMMANDES TELEGRAM
# ============================================================================

async def cmd_command1(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /command1 - Message de bienvenue"""
    welcome_msg = """🚀 *Bienvenue sur Multi-Chain Arbitrage Bot !*

Je surveille en permanence les opportunités d'arbitrage sur **Solana** et **Base**.

📊 *Tokens suivis:*
  • Solana: 5 tokens (PUMP, BONK, JUP, Virtual, Pyth)
  • Base: 3 tokens (Virtual, AERO, KTA)
  • **Total: 8 tokens**

🔄 *DEX surveillés:*
  • Solana: 6 DEX (Jupiter, Raydium, Orca, Meteora, PumpFun, OpenBook)
  • Base: 3 DEX (Aerodrome, Uniswap V3, PancakeSwap)
  • **Total: 9 DEX**

📈 *Spread minimum:* 2% (frais inclus)

🤖 *Commandes disponibles:*
/command1 - Message de bienvenue
/status - Statut du bot
/command3 - Liste de TOUS les tokens (Solana + Base)
/dex - Liste des DEX
/perf - Historique des arbitrages
/help - Aide

✅ *Le bot est actif 24/24h*
Vous recevrez une alerte dès qu'une opportunité > 2% sera détectée !

💡 *Nouveauté:* Support multi-chain (Solana + Base)
🕐 *Rapport automatique:* Tous les jours à 9h00 Paris

_Bon trading ! 💰_"""
    
    await update.message.reply_text(welcome_msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /status - Statut du bot"""
    # Importer ici pour éviter la dépendance circulaire
    try:
        from ui import bot_state
        
        uptime_seconds = bot_state.get_uptime_seconds()
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        
        status_msg = f"""📊 *STATUT DU BOT*

🟢 *Statut:* Actif 24/24h
⏱️ *Uptime:* {hours}h {minutes}m
🔍 *Opportunités trouvées:* {bot_state.opportunities_found}
📨 *Alertes envoyées:* {bot_state.alerts_sent}
⏰ *Dernière vérification:* Il y a quelques secondes

📈 *Configuration:*
• Spread minimum: 2%
• Intervalle: 60 secondes
• Tokens surveillés: 5
• DEX actifs: 6

🌐 *Dashboard Web:* http://localhost:8000

_Le bot scanne le marché en continu !_"""
        
    except ImportError:
        status_msg = """📊 *STATUT DU BOT*

🟢 *Statut:* Actif 24/24h
⏱️ *Uptime:* Calcul en cours...
🔍 *Scan:* En cours

📈 *Configuration:*
• Spread minimum: 2%
• Intervalle: 60 secondes
• Tokens surveillés: 5
• DEX actifs: 6

_Le bot scanne le marché en continu !_"""
    
    await update.message.reply_text(status_msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_command3(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /command3 - Liste de TOUS les tokens (Solana + Base)"""
    msg_lines = ["📋 *TOUS LES TOKENS SURVEILLÉS*\n"]
    
    # Section Solana
    msg_lines.append("⛓️ *BLOCKCHAIN SOLANA* (5 tokens)")
    msg_lines.append("")
    
    for i, (address, name) in enumerate(TRACKED_TOKENS_SOLANA.items(), 1):
        short_addr = truncate_address(address, 8, 4)
        msg_lines.append(f"{i}. *{name}*")
        msg_lines.append(f"   `{short_addr}`")
        msg_lines.append(f"   [Birdeye](https://birdeye.so/token/{address}?chain=solana)")
        msg_lines.append("")
    
    # Section Base
    msg_lines.append("⛓️ *BLOCKCHAIN BASE* (3 tokens)")
    msg_lines.append("")
    
    for i, (address, name) in enumerate(TRACKED_TOKENS_BASE.items(), 1):
        # Base addresses sont plus courtes (format Ethereum)
        short_addr = address[:6] + "..." + address[-4:]
        msg_lines.append(f"{i}. *{name}*")
        msg_lines.append(f"   `{short_addr}`")
        msg_lines.append(f"   [BaseScan](https://basescan.org/token/{address})")
        msg_lines.append("")
    
    msg_lines.append("📊 *Total:* 8 tokens sur 2 blockchains")
    msg_lines.append("🔄 *Vérification:* Toutes les 60 secondes")
    msg_lines.append("💰 *DEX surveillés:* 9 au total (6 Solana + 3 Base)")
    msg_lines.append("\n_Pour ajouter un token, modifiez le fichier .env_")
    
    tokens_msg = "\n".join(msg_lines)
    await update.message.reply_text(
        tokens_msg, 
        parse_mode=ParseMode.MARKDOWN,
        disable_web_page_preview=True
    )

async def cmd_dex(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /dex - Liste des DEX supportés"""
    msg_lines = ["🔄 *DEX SUPPORTÉS*\n"]
    
    for i, (dex_id, info) in enumerate(SUPPORTED_DEX.items(), 1):
        msg_lines.append(f"{i}. *{info['name']}*")
        msg_lines.append(f"   • Type: {info['type']}")
        msg_lines.append(f"   • Frais: {info['fee']}")
        msg_lines.append("")
    
    msg_lines.append("✅ *Le bot compare les prix sur TOUS ces DEX*")
    msg_lines.append("📊 *Stratégie:* Acheter sur le moins cher, vendre sur le plus cher")
    msg_lines.append("\n_Les spreads sont calculés après déduction de tous les frais_")
    
    dex_msg = "\n".join(msg_lines)
    await update.message.reply_text(dex_msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_perf(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /perf - Historique des performances"""
    if not opportunities_history:
        perf_msg = """📊 *HISTORIQUE DES ARBITRAGES*

🔍 Aucune opportunité détectée pour le moment.

Le bot scanne le marché toutes les 60 secondes.
Vous serez alerté dès qu'un spread > 2% sera trouvé !

💡 *Conseil:* Les opportunités sont rares mais réelles.
Patience et le bot vous alertera ! 🎯"""
        
        await update.message.reply_text(perf_msg, parse_mode=ParseMode.MARKDOWN)
        return
    
    # Limiter aux 10 dernières opportunités
    recent_opps = opportunities_history[-10:]
    
    msg_lines = [f"📊 *HISTORIQUE DES ARBITRAGES*\n"]
    msg_lines.append(f"Total détecté: *{len(opportunities_history)}* opportunités\n")
    
    for i, opp in enumerate(reversed(recent_opps), 1):
        token_name = TRACKED_TOKENS.get(opp.get('token', ''), 'Unknown')
        spread_net = opp.get('spread_net', 0)
        buy_dex = opp.get('buy_dex', '?').title()
        sell_dex = opp.get('sell_dex', '?').title()
        timestamp = opp.get('timestamp_str', 'N/A')
        
        msg_lines.append(f"{i}. *{token_name}* - {format_percentage(spread_net)}")
        msg_lines.append(f"   {buy_dex} → {sell_dex}")
        msg_lines.append(f"   _{timestamp}_")
        msg_lines.append("")
    
    if len(opportunities_history) > 10:
        msg_lines.append(f"_...et {len(opportunities_history) - 10} autres_")
    
    perf_msg = "\n".join(msg_lines)
    await update.message.reply_text(perf_msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /help - Aide"""
    help_msg = """ℹ️ *AIDE - COMMANDES DISPONIBLES*

🤖 *Commandes du bot:*
/start - Message de bienvenue
/status - Statut du bot en temps réel
/tokensuivies - Liste des 5 tokens surveillés
/dex - Liste des 6 DEX supportés
/perf - Historique des arbitrages détectés
/help - Afficher cette aide

📊 *Fonctionnement:*
Le bot scanne automatiquement les prix toutes les 60 secondes sur 6 DEX différents. Quand il détecte un spread > 2% (après déduction de TOUS les frais), il vous envoie une alerte ici.

🎯 *Que faire à la réception d'une alerte ?*
1. Vérifier la liquidité sur DexScreener
2. Simuler le trade mentalement ou sur Jupiter
3. Exécuter UNIQUEMENT si vous êtes sûr
4. Ne JAMAIS trader sans vérification

⚠️ *Important:*
• Ce bot NE trade PAS automatiquement
• Il ne fait QUE de la détection
• Toujours vérifier avant de trader
• Les marchés crypto sont risqués

🌐 *Dashboard Web:*
http://localhost:8000

_Bon trading ! 💰_"""
    
    await update.message.reply_text(help_msg, parse_mode=ParseMode.MARKDOWN)

async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Commande /test - Test de connexion et envoi de notification"""
    try:
        test_msg = """🧪 *TEST DE CONNEXION*

✅ *Le bot répond correctement !*

📱 *Statut:*
  • Bot actif: ✅
  • Commandes: ✅
  • Notifications: ✅

🚀 *Le bot est opérationnel !*

_Message de test envoyé le {datetime.utcnow().strftime('%d/%m/%Y %H:%M:%S')} UTC_""".format(
            datetime=datetime
        )
        
        await update.message.reply_text(test_msg, parse_mode=ParseMode.MARKDOWN)
        logger.info(f"Test command received from chat {update.effective_chat.id}")
    except Exception as e:
        logger.exception(f"Error in test command: {e}")
        await update.message.reply_text("❌ Erreur lors du test")

# ============================================================================
# GESTION DE L'APPLICATION TELEGRAM
# ============================================================================

async def start_telegram_app():
    """Démarre l'application Telegram avec les handlers de commandes"""
    if TELEGRAM_BOT_TOKEN is None:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Ajouter les handlers de commandes
    # Ajouter les handlers de commandes avec gestion d'erreurs
    async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
        """Gestionnaire d'erreurs global pour les commandes"""
        logger.error(f"Exception while handling an update: {context.error}")
        if update and hasattr(update, 'message') and update.message:
            try:
                await update.message.reply_text(
                    "❌ Une erreur s'est produite. Veuillez réessayer plus tard."
                )
            except:
                pass
    
    app.add_handler(CommandHandler("command1", cmd_command1))  # Bienvenue
    app.add_handler(CommandHandler("start", cmd_command1))  # Alias pour /start
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("command3", cmd_command3))  # Tous les tokens
    app.add_handler(CommandHandler("tokensuivies", cmd_command3))  # Alias
    app.add_handler(CommandHandler("dex", cmd_dex))
    app.add_handler(CommandHandler("perf", cmd_perf))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("test", cmd_test))  # Nouvelle commande de test
    
    # Ajouter le gestionnaire d'erreurs global
    app.add_error_handler(error_handler)
    
    await app.initialize()
    await app.start()
    
    # Démarrer le polling pour écouter les commandes
    # IMPORTANT: start_polling() démarre en arrière-plan et ne bloque PAS
    try:
        # start_polling() démarre le polling en arrière-plan (non-bloquant)
        app.updater.start_polling(
            drop_pending_updates=True,
            allowed_updates=["message", "callback_query"]
        )
        logger.info("✅ Telegram polling started successfully (non-blocking)")
    except Exception as e:
        logger.exception(f"❌ Failed to start Telegram polling: {e}")
        # On continue quand même, mais les commandes ne fonctionneront pas
        logger.warning("⚠️  Telegram commands may not work, but alerts can still be sent")
    
    # Vérifier que le bot est bien connecté
    try:
        bot_info = await app.bot.get_me()
        logger.info(f"✅ Bot verified: @{bot_info.username} ({bot_info.first_name})")
    except Exception as e:
        logger.error(f"❌ Failed to verify bot: {e}")
    
    logger.info("Telegram app started with command handlers")
    return app

async def stop_telegram_app(app: Application):
    """Arrête proprement l'application Telegram"""
    try:
        if app and app.updater:
            await app.updater.stop()
        if app:
            await app.stop()
            await app.shutdown()
        logger.info("✅ Telegram app stopped successfully")
    except Exception as e:
        logger.error(f"Error stopping Telegram app: {e}")

def add_to_history(opp: dict):
    """Ajoute une opportunité à l'historique"""
    global opportunities_history
    
    # Ajouter timestamp lisible
    opp_copy = opp.copy()
    opp_copy['timestamp_str'] = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    
    opportunities_history.append(opp_copy)
    
    # Garder seulement les 100 dernières
    if len(opportunities_history) > 100:
        opportunities_history = opportunities_history[-100:]

async def send_opportunity(app: Application, chat_id: int, opp: dict):
    """
    Construit et envoie un message d'alerte Telegram formaté.
    
    Supporte les chaînes Solana et Base.
    
    Args:
        app: Application Telegram
        chat_id: ID du chat destinataire
        opp: Dict retourné par arbitrage.compute_spread_and_metrics
    """
    # Emojis pour rendre le message plus lisible
    emoji_fire = "🔥"
    emoji_chart = "📊"
    emoji_money = "💰"
    emoji_dex = "🔄"
    emoji_check = "✅"
    emoji_warning = "⚠️"
    emoji_rocket = "🚀"
    
    # Détecter la chaîne
    chain = opp.get("chain", "solana").lower()
    is_base = chain == "base"
    chain_emoji = "🔵" if is_base else "🟣"
    chain_name = "BASE" if is_base else "SOLANA"
    
    # Extraire les données
    token = opp.get("token", "Unknown")
    token_short = token[:8] + "..." + token[-4:]
    
    buy_dex = opp.get("buy_dex", "?").title()
    sell_dex = opp.get("sell_dex", "?").title()
    buy_price = opp.get("buy_price", 0)
    sell_price = opp.get("sell_price", 0)
    
    spread_brut = opp.get("spread_brut", 0)
    spread_net = opp.get("spread_net", 0)
    
    # Base a une structure de frais différente
    if is_base:
        fees = opp.get("fees", {})
        total_costs = fees.get("total", 0)
        liquidity = opp.get("liquidity", 0)
        volume_24h = 0  # Pas disponible pour Base
        confidence_score = opp.get("confidence", 0)
        dex_count = opp.get("dex_count", 0)
    else:
        total_costs = opp.get("total_costs", 0)
        liquidity = opp.get("liquidity_usd", 0)
        volume_24h = opp.get("volume_24h", 0)
        confidence_score = opp.get("confidence_score", 0)
        dex_count = opp.get("dex_count", 0)
    
    # Déterminer le niveau d'opportunité
    if spread_net >= 0.03:  # >= 3%
        level_emoji = f"{emoji_fire}{emoji_fire}{emoji_fire}"
        level_text = "EXCELLENTE"
    elif spread_net >= 0.015:  # >= 1.5%
        level_emoji = f"{emoji_fire}{emoji_fire}"
        level_text = "TRÈS BONNE"
    elif spread_net >= 0.01:  # >= 1%
        level_emoji = emoji_fire
        level_text = "BONNE"
    else:
        level_emoji = emoji_check
        level_text = "INTÉRESSANTE"
    
    # Emoji pour le score de confiance
    if confidence_score >= 80:
        score_emoji = "🟢"
        score_text = "ÉLEVÉ"
    elif confidence_score >= 60:
        score_emoji = "🟡"
        score_text = "MOYEN"
    else:
        score_emoji = "🔴"
        score_text = "FAIBLE"
    
    # Construction du message
    text = [
        f"{emoji_rocket} *OPPORTUNITÉ D'ARBITRAGE {level_emoji}*",
        f"_{level_text}_ {chain_emoji} *{chain_name}*",
        "",
        f"*Token:* `{token_short}`",
        "",
        f"🔒 *Score confiance:* {score_emoji} {confidence_score}% ({score_text})",
        f"   _Basé sur {dex_count} DEX avec prix_",
        "",
        f"{emoji_dex} *Stratégie Pool-to-Pool:*",
        f"  • Acheter sur *{buy_dex}* @ `{buy_price:.8f}`",
        f"  • Vendre sur *{sell_dex}* @ `{sell_price:.8f}`",
        "",
        f"{emoji_chart} *Spreads:*",
        f"  • Spread brut: `{spread_brut*100:.2f}%`",
        f"  • Coûts totaux: `{total_costs*100:.2f}%`",
        f"  • *Spread net: `{spread_net*100:.2f}%`* {emoji_check}",
        "",
        f"💸 *Frais des pools:*",
    ]
    
    # Afficher les frais réels des pools
    details = opp.get("details", {})
    buy_pool_fee = details.get("buy_pool_fee_pct") or details.get("buy_dex_fee") or 0
    sell_pool_fee = details.get("sell_pool_fee_pct") or details.get("sell_dex_fee") or 0
    
    if buy_pool_fee > 0 or sell_pool_fee > 0:
        text.append(f"  • Buy pool fee: `{buy_pool_fee*100:.2f}%`")
        text.append(f"  • Sell pool fee: `{sell_pool_fee*100:.2f}%`")
    else:
        # Fallback pour ancien format
        if is_base and opp.get("fees"):
            fees = opp["fees"]
            if fees.get("dex_buy"):
                text.append(f"  • Buy pool fee: `{fees['dex_buy']*100:.2f}%`")
            if fees.get("dex_sell"):
                text.append(f"  • Sell pool fee: `{fees['dex_sell']*100:.2f}%`")
    
    # Extraire les URLs et frais des pools (nouveau format pool-to-pool)
    buy_pool_url = opp.get("buy_pool_url")
    sell_pool_url = opp.get("sell_pool_url")
    
    text.extend([
        "",
        f"{emoji_money} *Profit estimé (1000 USD):*",
        f"  • Net: `${spread_net * 1000:.2f}` USD",
        "",
    ])
    
    # Ajouter les liens de pools si disponibles
    if buy_pool_url or sell_pool_url:
        text.append("🔗 *Liens des pools:*")
        if buy_pool_url:
            text.append(f"  • BUY Pool: {buy_pool_url}")
        if sell_pool_url:
            text.append(f"  • SELL Pool: {sell_pool_url}")
        text.append("")
    
    # Détails des frais pour Base
    if is_base and opp.get("fees"):
        fees = opp["fees"]
        text.append("💸 *Détail des frais (Base):*")
        if fees.get("dex_buy"):
            text.append(f"  • DEX achat: `{fees['dex_buy']*100:.2f}%`")
        if fees.get("dex_sell"):
            text.append(f"  • DEX vente: `{fees['dex_sell']*100:.2f}%`")
        if fees.get("slippage"):
            text.append(f"  • Slippage: `{fees['slippage']*100:.2f}%`")
        if fees.get("mev"):
            text.append(f"  • MEV: `{fees['mev']*100:.2f}%`")
        if fees.get("price_impact"):
            text.append(f"  • Impact prix: `{fees['price_impact']*100:.3f}%`")
        text.append("")
    
    # Ajouter infos de liquidité si disponibles
    if liquidity > 0 or volume_24h > 0:
        text.append("📈 *Métriques:*")
        if liquidity > 0:
            text.append(f"  • Liquidité: `${liquidity:,.0f}`")
        if volume_24h > 0:
            text.append(f"  • Volume 24h: `${volume_24h:,.0f}`")
        text.append("")
    
    # Avertissements si nécessaire
    warnings = []
    if liquidity < 50000 and liquidity > 0:
        warnings.append(f"{emoji_warning} Liquidité faible")
    if volume_24h < 100000 and volume_24h > 0:
        warnings.append(f"{emoji_warning} Volume faible")
    
    # MEV warning for Base
    if is_base and opp.get("fees", {}).get("mev", 0) > 0.002:
        warnings.append(f"{emoji_warning} Risque MEV élevé")
    
    if warnings:
        text.extend(warnings)
        text.append("")
    
    # Note de sécurité
    text.append("_⚠️ Toujours simuler avant d'exécuter_")
    text.append("_🔒 Vérifier la liquidité réelle on-chain_")

    full_text = "\n".join(text)

    # Boutons pour liens POOLS (pool-to-pool)
    buttons = []
    
    # Générer liens vers explorateurs selon la chaîne
    if is_base:
        explorer_url = f"https://basescan.org/token/{token}"
        buttons.append([
            InlineKeyboardButton("🔍 BaseScan", url=explorer_url)
        ])
    else:
        birdeye_url = f"https://birdeye.so/token/{token}?chain=solana"
        buttons.append([
            InlineKeyboardButton("🦅 Birdeye", url=birdeye_url)
        ])
    
    # NOUVEAU: Liens directs vers les POOLS (pool-to-pool)
    buy_pool_url = opp.get("buy_pool_url")
    sell_pool_url = opp.get("sell_pool_url")
    
    if buy_pool_url:
        buttons.append([
            InlineKeyboardButton(f"🔗 BUY Pool ({buy_dex})", url=buy_pool_url)
        ])
    if sell_pool_url:
        buttons.append([
            InlineKeyboardButton(f"🔗 SELL Pool ({sell_dex})", url=sell_pool_url)
        ])
    
    # Fallback pour Base (ancien format)
    if is_base and not buy_pool_url:
        buy_url = opp.get("buy_url")
        sell_url = opp.get("sell_url")
        if buy_url:
            buttons.append([InlineKeyboardButton(f"💰 Acheter sur {buy_dex}", url=buy_url)])
        if sell_url:
            buttons.append([InlineKeyboardButton(f"💸 Vendre sur {sell_dex}", url=sell_url)])

    reply_markup = InlineKeyboardMarkup(buttons) if buttons else None
    
    # Envoyer le message
    try:
        await app.bot.send_message(
            chat_id=chat_id, 
            text=full_text, 
            parse_mode=ParseMode.MARKDOWN, 
            reply_markup=reply_markup,
            disable_web_page_preview=True  # Éviter les previews lourds
        )
        # Ajouter à l'historique
        add_to_history(opp)
        
        logger.info(f"✅ [{chain_name}] Alert sent for {token_short} | Spread: {spread_net*100:.2f}%")
    except Exception as e:
        logger.exception(f"❌ Failed to send telegram message: {e}")
