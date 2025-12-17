# pool_prices.py
"""
Module pour structurer les prix pool-to-pool.

Ce module prend les pools récupérées par pool_fetchers.py et:
1. Filtre les pools contenant un token spécifique
2. Calcule les prix buy/sell pour chaque pool
3. Génère les URLs directes vers les pools
4. Structure les données pour l'arbitrage pool-to-pool
"""
from typing import List, Dict, Optional, Any
from pool_fetchers import fetch_all_pools, USDC_MINT, SOL_MINT
from utils import logger


# ============================================================================
# URL GENERATORS
# ============================================================================

def get_pool_url(dex: str, pool_id: str, chain: str = "solana") -> str:
    """
    Génère l'URL directe vers une pool selon le DEX avec templates robustes.

    Templates par DEX:
    - Solana:
      - Raydium: https://raydium.io/pool/{POOL_ID}
      - Orca: https://www.orca.so/whirlpools/{POOL_ID}
      - Meteora: https://app.meteora.ag/pool/{POOL_ID}
      - Lifinity: https://app.lifinity.io/pool/{POOL_ID}
      - Phoenix: https://app.phoenix.trade/market/{POOL_ID}
    - Base:
      - Uniswap V3: https://app.uniswap.org/explore/pools/base/{POOL_ID}
      - Aerodrome: https://aerodrome.finance/pools/{POOL_ID}
      - PancakeSwap: https://pancakeswap.finance/add?chain=base&tokenA={TOKENA}&tokenB={TOKENB}

    Fallback: Explorer blockchain uniquement si DEX inconnu
    """
    dex_lower = dex.lower()
    chain_lower = chain.lower()

    # Templates par chaîne et DEX
    url_templates = {
        "solana": {
            "raydium": "https://raydium.io/pool/{pool_id}",
            "orca": "https://www.orca.so/whirlpools/{pool_id}",
            "meteora": "https://app.meteora.ag/pool/{pool_id}",
            "lifinity": "https://app.lifinity.io/pool/{pool_id}",
            "phoenix": "https://app.phoenix.trade/market/{pool_id}",
        },
        "base": {
            "uniswap": "https://app.uniswap.org/explore/pools/base/{pool_id}",
            "aerodrome": "https://aerodrome.finance/pools/{pool_id}",
            "pancakeswap": "https://pancakeswap.finance/add?chain=base",
            "kyberswap": "https://kyberswap.com/swap/base",
        }
    }

    # Essayer de trouver le template pour cette chaîne/DEX
    if chain_lower in url_templates and dex_lower in url_templates[chain_lower]:
        template = url_templates[chain_lower][dex_lower]
        try:
            return template.format(pool_id=pool_id)
        except (KeyError, ValueError) as e:
            logger.warning(f"[URL] Template error for {chain}/{dex}: {e}")

    # Fallback vers explorer blockchain
    if chain_lower == "solana":
        return f"https://explorer.solana.com/address/{pool_id}"
    elif chain_lower == "base":
        return f"https://basescan.org/address/{pool_id}"
    else:
        return f"https://explorer.solana.com/address/{pool_id}"  # fallback par défaut


# ============================================================================
# PRICE CALCULATION FROM POOLS
# ============================================================================

def normalize_price_for_token(
    pool: Dict[str, Any],
    token_mint: str,
    base_mint: str = SOL_MINT
) -> Optional[Dict[str, Any]]:
    """
    Normalise le prix d'une pool pour un token spécifique.
    
    Args:
        pool: Pool dict depuis pool_fetchers
        token_mint: Token à évaluer
        base_mint: Token de base (SOL ou USDC)
    
    Returns:
        {
            "buy_price": prix pour acheter token avec base,
            "sell_price": prix pour vendre token contre base,
            "pool_id": ...
            "dex": ...
            "fee_pct": ...
            "url": ...
        }
    """
    token_a = pool.get("token_a")
    token_b = pool.get("token_b")
    price = pool.get("price")
    
    if not price or not token_a or not token_b:
        return None
    
    buy_price = None
    sell_price = None
    
    # Cas 1: token_a == token_mint, token_b == base_mint
    if token_a == token_mint and token_b == base_mint:
        buy_price = 1.0 / price  # Pour acheter token, on donne base
        sell_price = price  # Pour vendre token, on reçoit base
    
    # Cas 2: token_a == base_mint, token_b == token_mint
    elif token_a == base_mint and token_b == token_mint:
        buy_price = price  # Pour acheter token, on donne base
        sell_price = 1.0 / price  # Pour vendre token, on reçoit base
    
    else:
        # Pool n'a pas le bon pair
        return None
    
    if buy_price is None or sell_price is None or buy_price <= 0 or sell_price <= 0:
        return None
    
    return {
        "pool_id": pool.get("pool_id"),
        "dex": pool.get("dex"),
        "buy_price": buy_price,
        "sell_price": sell_price,
        "fee_pct": pool.get("fee_pct", 0),
        "fee_bps": pool.get("fee_bps", 0),
        "liquidity_usd": pool.get("liquidity_usd", 0),
        "url": get_pool_url(pool.get("dex"), pool.get("pool_id")),
        "pool_type": pool.get("pool_type"),
    }


# ============================================================================
# MAIN FUNCTION: GET POOL PRICES FOR TOKEN
# ============================================================================

async def get_pool_prices_for_token(
    session,
    token_mint: str,
    base_mint: str = SOL_MINT,
    all_pools: Optional[Dict[str, List[Dict[str, Any]]]] = None
) -> List[Dict[str, Any]]:
    """
    Retourne toutes les pools contenant un token avec leurs prix buy/sell.
    
    Args:
        session: aiohttp session
        token_mint: Token à analyser
        base_mint: Token de base (SOL ou USDC)
        all_pools: Pools déjà récupérées (optionnel, pour éviter de refetch)
    
    Returns:
        Liste de pools structurées:
        [
            {
                "dex": "raydium",
                "pool_id": "...",
                "buy_price": 0.00123,
                "sell_price": 0.00120,
                "fee_pct": 0.0025,
                "fee_bps": 25,
                "liquidity_usd": 50000,
                "url": "https://...",
            },
            ...
        ]
    """
    # Récupérer toutes les pools si non fournies
    if all_pools is None:
        all_pools = await fetch_all_pools(session)
    
    result = []
    
    # Parcourir tous les DEX
    for dex_name, pools_list in all_pools.items():
        for pool in pools_list:
            normalized = normalize_price_for_token(pool, token_mint, base_mint)
            if normalized:
                result.append(normalized)
    
    logger.debug(f"Found {len(result)} pools for token {token_mint[:8]}...")
    
    return result


# ============================================================================
# HELPER: FILTER POOLS BY LIQUIDITY
# ============================================================================

def filter_pools_by_liquidity(
    pools: List[Dict[str, Any]],
    min_liquidity_usd: float = 10000
) -> List[Dict[str, Any]]:
    """Filtre les pools par liquidité minimum."""
    return [
        p for p in pools
        if p.get("liquidity_usd", 0) >= min_liquidity_usd
    ]


# ============================================================================
# HELPER: SORT POOLS BY PRICE
# ============================================================================

def sort_pools_by_buy_price(pools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trie les pools par prix d'achat (croissant)."""
    return sorted(pools, key=lambda p: p.get("buy_price", float("inf")))


def sort_pools_by_sell_price(pools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trie les pools par prix de vente (décroissant)."""
    return sorted(pools, key=lambda p: p.get("sell_price", 0), reverse=True)



