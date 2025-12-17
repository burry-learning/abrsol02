# base_chain_integration.py
"""
Module d'intégration pour la blockchain Base.

Ce module fournit des fonctions utilitaires pour interagir avec les DEX Base.
Les fonctions principales de récupération de prix sont dans base_dex_fetchers.py.

Ce fichier peut être utilisé comme point d'entrée pour d'autres intégrations Base.
"""
import asyncio
import aiohttp
from typing import Dict, Optional, List
from utils import logger

# Import des fonctions principales depuis base_dex_fetchers
try:
    from base_dex_fetchers import (
        get_all_base_dex_prices,
        get_uniswap_price,
        get_aerodrome_price,
        get_pancakeswap_price,
        get_kyberswap_price,
        USDC_BASE,
        WETH_BASE,
        BASE_DEX_FEES,
    )
    BASE_FETCHERS_AVAILABLE = True
except ImportError:
    BASE_FETCHERS_AVAILABLE = False
    logger.warning("base_dex_fetchers non disponible")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def get_base_token_price_direct(
    session: aiohttp.ClientSession,
    token_address: str,
    base_token: str = USDC_BASE
) -> Optional[float]:
    """
    Récupère le prix d'un token Base en USDC depuis les DEX natifs.
    
    Args:
        session: Session aiohttp
        token_address: Adresse du token Base
        base_token: Token de base (par défaut USDC)
    
    Returns:
        Prix en USDC ou None si erreur
    """
    if not BASE_FETCHERS_AVAILABLE:
        return None
    
    try:
        dex_prices = await get_all_base_dex_prices(session, token_address, base_token)
        if not dex_prices:
            return None
        
        # Retourner le prix moyen de tous les DEX
        prices = list(dex_prices.values())
        if prices:
            return sum(prices) / len(prices)
        return None
    
    except Exception as e:
        logger.error(f"Erreur récupération prix Base {token_address[:8]}: {e}")
        return None


async def get_base_token_prices_all_dex(
    session: aiohttp.ClientSession,
    token_address: str,
    base_token: str = USDC_BASE
) -> Dict[str, float]:
    """
    Récupère les prix d'un token Base depuis tous les DEX disponibles.
    
    Args:
        session: Session aiohttp
        token_address: Adresse du token Base
        base_token: Token de base (par défaut USDC)
    
    Returns:
        Dict {dex_name: price} ou dict vide si erreur
    """
    if not BASE_FETCHERS_AVAILABLE:
        return {}
    
    try:
        return await get_all_base_dex_prices(session, token_address, base_token) or {}
    except Exception as e:
        logger.error(f"Erreur récupération prix Base tous DEX {token_address[:8]}: {e}")
        return {}


def get_base_token_info(token_address: str) -> Dict[str, str]:
    """
    Retourne des informations sur un token Base connu.
    
    Args:
        token_address: Adresse du token
    
    Returns:
        Dict avec name, symbol, etc.
    """
    known_tokens = {
        "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b": {
            "name": "Virtual Protocol",
            "symbol": "VIRTUAL",
            "decimals": 18
        },
        "0x532f27101965dd16442e59d40670faf5ebb142e4": {
            "name": "Brett",
            "symbol": "BRETT",
            "decimals": 18
        },
        "0xac1bd2486aaf3b5c0fc3fd868558b082a531b2b4": {
            "name": "Toshi",
            "symbol": "TOSHI",
            "decimals": 18
        },
        USDC_BASE: {
            "name": "USD Coin",
            "symbol": "USDC",
            "decimals": 6
        },
        WETH_BASE: {
            "name": "Wrapped Ether",
            "symbol": "WETH",
            "decimals": 18
        },
    }
    
    return known_tokens.get(token_address, {
        "name": "Unknown",
        "symbol": token_address[:6].upper(),
        "decimals": 18
    })


# =============================================================================
# MAIN USAGE
# =============================================================================

async def main():
    """Exemple d'utilisation."""
    async with aiohttp.ClientSession() as session:
        # Exemple: récupérer le prix de VIRTUAL
        token = "0x0b3e328455c4059EEb9e3f84b5543F74E24e7E1b"
        prices = await get_base_token_prices_all_dex(session, token)
        print(f"Prix VIRTUAL depuis tous les DEX: {prices}")


if __name__ == "__main__":
    asyncio.run(main())

