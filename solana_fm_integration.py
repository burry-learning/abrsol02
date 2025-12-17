#!/usr/bin/env python3
# solana_fm_integration.py
"""
Intégration Solana FM pour détecter les niveaux de slippage élevés.

Fonctionnalités:
- Récupération des métadonnées et prix des tokens
- Analyse du slippage historique
- Détection des niveaux de slippage anormaux
- Respect des limites de rate (100 req/min)

Documentation Solana FM: https://docs.solana.fm/
"""

import asyncio
import aiohttp
import os
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from utils import logger

# Configuration Solana FM
SOLANA_FM_API_KEY = os.getenv("SOLANA_FM_API_KEY", "")
SOLANA_FM_BASE_URL = "https://api.solana.fm/v0"

# Limites de rate (100 req/min)
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # secondes

# Seuils de slippage (en décimal)
HIGH_SLIPPAGE_THRESHOLD = 0.02  # 2%
CRITICAL_SLIPPAGE_THRESHOLD = 0.05  # 5%

# Cache pour éviter trop de requêtes
_cache = {}
_request_count = 0
_request_window_start = datetime.utcnow()

# ============================================================================
# Gestion du Rate Limiting
# ============================================================================

async def _check_rate_limit():
    """Vérifie et applique les limites de rate"""
    global _request_count, _request_window_start
    
    now = datetime.utcnow()
    time_since_window_start = (now - _request_window_start).total_seconds()
    
    # Reset du compteur si nouvelle fenêtre
    if time_since_window_start >= RATE_LIMIT_WINDOW:
        _request_count = 0
        _request_window_start = now
        return
    
    # Si limite atteinte, attendre
    if _request_count >= RATE_LIMIT_REQUESTS:
        wait_time = RATE_LIMIT_WINDOW - time_since_window_start
        logger.warning(f"Solana FM rate limit reached, waiting {wait_time:.0f}s")
        await asyncio.sleep(wait_time)
        _request_count = 0
        _request_window_start = datetime.utcnow()
    
    _request_count += 1

# ============================================================================
# Fonctions API Solana FM
# ============================================================================

async def get_token_info(
    session: aiohttp.ClientSession,
    token_address: str
) -> Optional[Dict[str, Any]]:
    """
    Récupère les métadonnées et prix d'un token via Solana FM.
    
    Args:
        session: Session HTTP aiohttp
        token_address: Adresse du token Solana
    
    Returns:
        Dict avec métadonnées ou None si erreur
    """
    if not SOLANA_FM_API_KEY:
        logger.debug("Solana FM API key not configured")
        return None
    
    # Vérifier le cache (5 minutes)
    cache_key = f"token_info_{token_address}"
    if cache_key in _cache:
        cached_data, cached_time = _cache[cache_key]
        if (datetime.utcnow() - cached_time).total_seconds() < 300:  # 5 min
            return cached_data
    
    # Rate limiting
    await _check_rate_limit()
    
    url = f"{SOLANA_FM_BASE_URL}/tokens/{token_address}"
    headers = {
        "Authorization": f"Bearer {SOLANA_FM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                # Mettre en cache
                _cache[cache_key] = (data, datetime.utcnow())
                
                logger.debug(f"Solana FM: Token info retrieved for {token_address[:8]}")
                return data
            elif resp.status == 429:
                logger.warning("Solana FM: Rate limit exceeded")
            else:
                logger.debug(f"Solana FM: Non-200 status {resp.status}")
    except asyncio.TimeoutError:
        logger.debug("Solana FM: Request timeout")
    except Exception as e:
        logger.debug(f"Solana FM: Error {e}")
    
    return None

async def get_transaction_details(
    session: aiohttp.ClientSession,
    tx_signature: str
) -> Optional[Dict[str, Any]]:
    """
    Récupère les détails d'une transaction via Solana FM.
    
    Args:
        session: Session HTTP aiohttp
        tx_signature: Signature de la transaction
    
    Returns:
        Dict avec détails ou None si erreur
    """
    if not SOLANA_FM_API_KEY:
        return None
    
    # Rate limiting
    await _check_rate_limit()
    
    url = f"{SOLANA_FM_BASE_URL}/transactions/{tx_signature}"
    headers = {
        "Authorization": f"Bearer {SOLANA_FM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data
            else:
                logger.debug(f"Solana FM: Non-200 status {resp.status}")
    except Exception as e:
        logger.debug(f"Solana FM: Error {e}")
    
    return None

# ============================================================================
# Analyse du Slippage
# ============================================================================

async def analyze_token_slippage(
    session: aiohttp.ClientSession,
    token_address: str
) -> Dict[str, Any]:
    """
    Analyse le slippage historique d'un token.
    
    Args:
        session: Session HTTP aiohttp
        token_address: Adresse du token
    
    Returns:
        Dict avec analyse du slippage:
        - average_slippage: Slippage moyen (décimal)
        - max_slippage: Slippage maximum observé
        - is_high_slippage: Boolean si slippage élevé
        - is_critical_slippage: Boolean si slippage critique
        - recommendation: Recommandation (safe/caution/danger)
    """
    token_info = await get_token_info(session, token_address)
    
    if not token_info:
        # Pas de données Solana FM, utiliser des valeurs par défaut conservatrices
        return {
            "average_slippage": 0.01,  # 1% par défaut
            "max_slippage": 0.02,
            "is_high_slippage": False,
            "is_critical_slippage": False,
            "recommendation": "unknown",
            "data_source": "default"
        }
    
    # Extraire les données de slippage depuis Solana FM
    # Note: La structure exacte dépend de l'API Solana FM
    # Adapter selon la documentation réelle
    
    try:
        # Exemple d'extraction (à adapter selon la vraie structure)
        price_data = token_info.get("price", {})
        volume_24h = float(token_info.get("volume24h", 0))
        liquidity = float(token_info.get("liquidity", 0))
        
        # Estimation du slippage basée sur liquidité/volume
        if liquidity > 0:
            estimated_slippage = min(0.5, volume_24h / (liquidity * 100))
        else:
            estimated_slippage = 0.05  # 5% si pas de données
        
        max_slippage = estimated_slippage * 1.5
        
        is_high = estimated_slippage >= HIGH_SLIPPAGE_THRESHOLD
        is_critical = estimated_slippage >= CRITICAL_SLIPPAGE_THRESHOLD
        
        # Recommandation
        if is_critical:
            recommendation = "danger"
        elif is_high:
            recommendation = "caution"
        else:
            recommendation = "safe"
        
        return {
            "average_slippage": estimated_slippage,
            "max_slippage": max_slippage,
            "is_high_slippage": is_high,
            "is_critical_slippage": is_critical,
            "recommendation": recommendation,
            "liquidity": liquidity,
            "volume_24h": volume_24h,
            "data_source": "solana_fm"
        }
        
    except Exception as e:
        logger.error(f"Error analyzing slippage: {e}")
        return {
            "average_slippage": 0.02,
            "max_slippage": 0.05,
            "is_high_slippage": True,
            "is_critical_slippage": False,
            "recommendation": "caution",
            "data_source": "error"
        }

async def should_trade_token(
    session: aiohttp.ClientSession,
    token_address: str,
    max_acceptable_slippage: float = 0.02
) -> tuple[bool, str]:
    """
    Détermine si un token est safe pour trader basé sur le slippage.
    
    Args:
        session: Session HTTP aiohttp
        token_address: Adresse du token
        max_acceptable_slippage: Slippage maximum acceptable
    
    Returns:
        Tuple (should_trade: bool, reason: str)
    """
    analysis = await analyze_token_slippage(session, token_address)
    
    if analysis["is_critical_slippage"]:
        return False, f"❌ Slippage critique ({analysis['average_slippage']*100:.1f}%)"
    
    if analysis["average_slippage"] > max_acceptable_slippage:
        return False, f"⚠️ Slippage trop élevé ({analysis['average_slippage']*100:.1f}%)"
    
    if analysis["recommendation"] == "danger":
        return False, "❌ Recommandation: DANGER"
    
    if analysis["recommendation"] == "caution":
        return True, f"⚠️ Avec précaution (slippage: {analysis['average_slippage']*100:.1f}%)"
    
    return True, f"✅ Safe (slippage: {analysis['average_slippage']*100:.1f}%)"

# ============================================================================
# Intégration avec le Bot d'Arbitrage
# ============================================================================

async def enhance_opportunity_with_slippage(
    session: aiohttp.ClientSession,
    opportunity: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Enrichit une opportunité d'arbitrage avec des données de slippage.
    
    Args:
        session: Session HTTP aiohttp
        opportunity: Opportunité d'arbitrage
    
    Returns:
        Opportunité enrichie avec données de slippage
    """
    token_address = opportunity.get("token", "")
    
    if not token_address:
        return opportunity
    
    # Analyser le slippage
    slippage_analysis = await analyze_token_slippage(session, token_address)
    
    # Déterminer si tradable
    should_trade, reason = await should_trade_token(session, token_address)
    
    # Enrichir l'opportunité
    opportunity["slippage_analysis"] = slippage_analysis
    opportunity["is_tradable"] = should_trade
    opportunity["trade_recommendation"] = reason
    
    # Ajuster le spread net en tenant compte du slippage analysé
    if slippage_analysis["data_source"] == "solana_fm":
        additional_slippage = slippage_analysis["average_slippage"]
        opportunity["spread_net_adjusted"] = opportunity.get("spread_net", 0) - additional_slippage
    
    return opportunity

# ============================================================================
# Fonctions Utilitaires
# ============================================================================

def is_solana_fm_configured() -> bool:
    """Vérifie si Solana FM est configuré"""
    return bool(SOLANA_FM_API_KEY)

def get_slippage_warning_emoji(slippage: float) -> str:
    """Retourne un emoji selon le niveau de slippage"""
    if slippage >= CRITICAL_SLIPPAGE_THRESHOLD:
        return "🔴"
    elif slippage >= HIGH_SLIPPAGE_THRESHOLD:
        return "🟡"
    else:
        return "🟢"

# ============================================================================
# Configuration
# ============================================================================

def configure_solana_fm(api_key: str):
    """Configure la clé API Solana FM"""
    global SOLANA_FM_API_KEY
    SOLANA_FM_API_KEY = api_key
    logger.info("Solana FM configured")

# ============================================================================
# Test
# ============================================================================

async def test_solana_fm():
    """Test de l'intégration Solana FM"""
    if not SOLANA_FM_API_KEY:
        print("❌ Solana FM API key not configured")
        print("   Set SOLANA_FM_API_KEY in .env")
        return
    
    print("🧪 Testing Solana FM integration...")
    
    async with aiohttp.ClientSession() as session:
        # Test avec SOL
        sol_address = "So11111111111111111111111111111111111111112"
        
        print(f"\n📊 Analyzing SOL slippage...")
        analysis = await analyze_token_slippage(session, sol_address)
        
        print(f"   Average slippage: {analysis['average_slippage']*100:.2f}%")
        print(f"   Max slippage: {analysis['max_slippage']*100:.2f}%")
        print(f"   Recommendation: {analysis['recommendation']}")
        print(f"   Data source: {analysis['data_source']}")
        
        should_trade, reason = await should_trade_token(session, sol_address)
        print(f"\n   Should trade? {should_trade}")
        print(f"   Reason: {reason}")
    
    print("\n✅ Test completed")

if __name__ == "__main__":
    # Test de l'intégration
    asyncio.run(test_solana_fm())

