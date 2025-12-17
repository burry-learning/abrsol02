# pool_fetchers.py
"""
Module pour récupérer les POOLS natives de chaque DEX Solana.

Ce module récupère directement les pools (pas les prix agrégés) pour:
- Raydium CLMM v3
- Orca Whirlpool
- Meteora DLMM
- Lifinity v2
- Phoenix AMM (si disponible)

Chaque fetcher retourne une liste de pools avec:
- pool_id
- tokenA_mint, tokenB_mint
- price (calculé depuis la pool)
- liquidity (USD)
- fee_bps (frais de la pool en basis points)
- fee_pct (frais en pourcentage)
"""
import asyncio
import aiohttp
import time
import json
from typing import List, Dict, Optional, Any
from utils import logger
from config import (
    RAYDIUM_POOLS_API,
    ORCA_WHIRLPOOLS_API,
    METEORA_POOLS_API,
    PHOENIX_MARKETS_API,
    LIFINITY_POOLS_API,
    AERODROME_POOLS_API,
    KYBERSWAP_BASE_API,
)
from thegraph_fetcher import (
    get_pool_from_subgraph,
    get_static_pools_for_pair,
    sqrt_price_x96_to_price,
)

# USDC mint pour calculer les prix en USDC
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOL_MINT = "So11111111111111111111111111111111111111112"
BASE_USDC = "0x833589fcd6edb6e08f4c7c19962234ef8f82f18e"

# ============================================================================
# CACHE INTELLIGENT PAR (CHAIN, DEX, TOKEN) - TTL DYNAMIQUE
# ============================================================================
_smart_cache: Dict[str, Dict[str, Any]] = {}  # key: f"{chain}_{dex}_{token}", value: {"data": [...], "timestamp": float, "ttl": int}
MAX_RETRIES = 3  # Nombre max de tentatives
INITIAL_RETRY_DELAY = 1  # Délai initial en secondes
DEX_DOWN_TTL_SECONDS = 300  # TTL pour marquer un DEX down
_dex_down_until: Dict[str, float] = {}

# Cache global pour fetch_all_pools (legacy)
_pools_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
_cache_timestamp: float = 0.0
CACHE_TTL_SECONDS = 30  # TTL du cache global (30 secondes)

# Cache pour fetch_base_pools
_base_cache: Dict[str, Any] = {"timestamp": 0.0, "data": []}


def _get_cache_key(chain: str, dex: str, token: str = "") -> str:
    """Génère une clé de cache normalisée."""
    return f"{chain.lower()}_{dex.lower()}_{token}"


def _get_dynamic_ttl(liquidity_usd: float) -> int:
    """
    Calcule TTL dynamique basé sur la liquidité:
    - Haute liquidité (>500k USD): 10-15s
    - Moyenne liquidité (50k-500k): 30s
    - Basse liquidité (<50k): 60s
    """
    if liquidity_usd >= 500_000:
        return 15
    elif liquidity_usd >= 50_000:
        return 30
    else:
        return 60


def _get_cached_data(cache_key: str) -> Optional[List[Dict[str, Any]]]:
    """Récupère les données du cache si valides."""
    if cache_key not in _smart_cache:
        return None

    entry = _smart_cache[cache_key]
    current_time = time.time()
    age = current_time - entry["timestamp"]

    if age < entry["ttl"]:
        logger.debug(f"[CACHE] Using cached data for {cache_key} (age: {age:.1f}s)")
        return entry["data"]

    # Cache expiré, supprimer
    del _smart_cache[cache_key]
    return None


def _set_cached_data(cache_key: str, data: List[Dict[str, Any]], avg_liquidity: float = 100_000):
    """Stocke les données en cache avec TTL dynamique."""
    ttl = _get_dynamic_ttl(avg_liquidity)
    _smart_cache[cache_key] = {
        "data": data,
        "timestamp": time.time(),
        "ttl": ttl
    }
    logger.debug(f"[CACHE] Cached {len(data)} items for {cache_key} (TTL: {ttl}s)")


# ============================================================================
# HELPER: RETRY WITH EXPONENTIAL BACKOFF
# ============================================================================

async def fetch_with_retry(
    session: aiohttp.ClientSession,
    url: str,
    dex_name: str,
    timeout: int = 20,
    max_retries: int = MAX_RETRIES
) -> Optional[Dict]:
    """
    Fetch avec retry exponentiel et gestion d'erreurs robuste.
    
    Returns:
        Response JSON ou None si toutes les tentatives ont échoué
    """
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout, connect=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                elif resp.status == 429:  # Rate limit
                    wait_time = INITIAL_RETRY_DELAY * (2 ** attempt) + 1
                    logger.warning(f"{dex_name} rate limited (429), retrying in {wait_time}s...")
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.warning(f"{dex_name} API returned status {resp.status} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
        except asyncio.TimeoutError:
            logger.warning(f"{dex_name} timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
        except aiohttp.ClientError as e:
            logger.warning(f"{dex_name} client error: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
        except Exception as e:
            logger.error(f"{dex_name} unexpected error: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
    
    return None


# ============================================================================
# RAYDIUM CLMM v3
# ============================================================================

async def fetch_raydium_pools(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Récupère toutes les pools Raydium CLMM v3.
    
    Endpoint: https://api.raydium.io/v2/amm/pools (ou v3)
    
    Returns:
        Liste de pools avec: pool_id, tokenA, tokenB, price, liquidity, feeRate
    """
    url = RAYDIUM_POOLS_API
    pools = []
    
    data = await fetch_with_retry(session, url, "Raydium", timeout=15)
    if data:
        # Format peut varier selon l'API
        pools_data = data.get("data", []) if isinstance(data, dict) else data
        
        for pool in pools_data:
                    try:
                        pool_id = pool.get("poolId") or pool.get("id") or pool.get("address")
                        token_a = pool.get("tokenA") or pool.get("mintA") or pool.get("mint0")
                        token_b = pool.get("tokenB") or pool.get("mintB") or pool.get("mint1")
                        
                        # Prix peut être direct ou calculé depuis reserves
                        price = pool.get("price")
                        if not price:
                            # Calcul depuis reserves si disponible
                            reserve_a = pool.get("reserveA") or pool.get("reserve0")
                            reserve_b = pool.get("reserveB") or pool.get("reserve1")
                            if reserve_a and reserve_b and float(reserve_a) > 0:
                                price = float(reserve_b) / float(reserve_a)
                        
                        liquidity = float(pool.get("liquidity", 0) or pool.get("tvl", 0) or 0)
                        
                        # Frais en bps ou en pourcentage
                        fee_rate = pool.get("feeRate") or pool.get("fee") or 0
                        if isinstance(fee_rate, str):
                            fee_rate = float(fee_rate)
                        
                        # Convertir en bps si nécessaire (0.25% = 25 bps)
                        if fee_rate < 1:  # Probablement en pourcentage (0.0025)
                            fee_bps = int(fee_rate * 10000)
                        else:
                            fee_bps = int(fee_rate)
                        
                        fee_pct = fee_bps / 10000.0
                        
                        if pool_id and token_a and token_b:
                            pools.append({
                                "pool_id": pool_id,
                                "dex": "raydium",
                                "token_a": token_a,
                                "token_b": token_b,
                                "price": float(price) if price else None,
                                "liquidity_usd": liquidity,
                                "fee_bps": fee_bps,
                                "fee_pct": fee_pct,
                                "pool_type": "CLMM",
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing Raydium pool: {e}")
                        continue
    else:
        logger.warning("Raydium: All retry attempts failed")
    
    logger.info(f"Fetched {len(pools)} Raydium pools")
    return pools


# ============================================================================
# ORCA WHIRLPOOL
# ============================================================================

async def fetch_orca_whirlpools(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Récupère toutes les Whirlpools Orca.
    
    Endpoint: https://api.mainnet.orca.so/v1/whirlpool/list
    
    Returns:
        Liste de pools avec: pool_id, tokenA, tokenB, sqrtPrice, liquidity, feeTier
    """
    url = ORCA_WHIRLPOOLS_API
    pools = []
    
    data = await fetch_with_retry(session, url, "Orca", timeout=15)
    if data:
        whirlpools = data.get("whirlpools", []) if isinstance(data, dict) else data
        
        for wp in whirlpools:
                    try:
                        pool_id = wp.get("address") or wp.get("whirlpool")
                        token_a = wp.get("tokenA") or wp.get("tokenMintA")
                        token_b = wp.get("tokenB") or wp.get("tokenMintB")
                        
                        # Orca utilise sqrtPrice (Q64.64 format)
                        sqrt_price = wp.get("sqrtPrice") or wp.get("price")
                        price = None
                        
                        if sqrt_price:
                            try:
                                # Conversion sqrtPrice → price
                                # sqrtPrice est en Q64.64, il faut le convertir
                                sqrt_val = float(sqrt_price)
                                # Approximation: price ≈ (sqrtPrice / 2^64)^2
                                # Simplification pour le calcul
                                price = (sqrt_val / (2**64))**2
                                
                                # Ajuster selon les decimals si disponibles
                                decimals_a = int(wp.get("tokenADecimals", 9))
                                decimals_b = int(wp.get("tokenBDecimals", 9))
                                if decimals_a != decimals_b:
                                    price *= (10 ** (decimals_a - decimals_b))
                            except (ValueError, TypeError):
                                pass
                        
                        liquidity = float(wp.get("liquidity", 0) or wp.get("tvl", 0) or 0)
                        
                        # Fee tier en bps (300 = 0.3%, 2200 = 0.22%, etc.)
                        fee_tier = int(wp.get("feeTier", 0) or wp.get("fee", 300))
                        fee_bps = fee_tier if fee_tier > 0 else 300  # Default 0.3%
                        fee_pct = fee_bps / 10000.0
                        
                        if pool_id and token_a and token_b:
                            pools.append({
                                "pool_id": pool_id,
                                "dex": "orca",
                                "token_a": token_a,
                                "token_b": token_b,
                                "price": price,
                                "liquidity_usd": liquidity,
                                "fee_bps": fee_bps,
                                "fee_pct": fee_pct,
                                "pool_type": "Whirlpool",
                                "sqrt_price": sqrt_price,
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing Orca pool: {e}")
                        continue
    else:
        logger.warning("Orca: All retry attempts failed")
    
    logger.info(f"Fetched {len(pools)} Orca Whirlpools")
    return pools


# ============================================================================
# METEORA DLMM
# ============================================================================

async def fetch_meteora_pools(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Récupère toutes les pools Meteora DLMM.
    
    Endpoint: https://dlmm-api.meteora.ag/pools
    
    Returns:
        Liste de pools avec: pool_id, mint_x, mint_y, current_price, liquidity, feeBps
    """
    url = "https://dlmm-api.meteora.ag/pools"
    pools = []
    
    data = await fetch_with_retry(session, url, "Meteora", timeout=15)
    if data:
        pools_data = data if isinstance(data, list) else data.get("pools", [])
        
        for pool in pools_data:
                    try:
                        pool_id = pool.get("address") or pool.get("pool_id")
                        mint_x = pool.get("mint_x") or pool.get("tokenMintX")
                        mint_y = pool.get("mint_y") or pool.get("tokenMintY")
                        
                        # Meteora utilise current_price directement
                        current_price = pool.get("current_price") or pool.get("price")
                        price = float(current_price) if current_price else None
                        
                        liquidity = float(pool.get("liquidity", 0) or pool.get("tvl", 0) or 0)
                        
                        # Fee en bps
                        fee_bps = int(pool.get("fee_bps", 0) or pool.get("feeBps", 0) or 100)  # Default 0.1%
                        fee_pct = fee_bps / 10000.0
                        
                        if pool_id and mint_x and mint_y and price:
                            pools.append({
                                "pool_id": pool_id,
                                "dex": "meteora",
                                "token_a": mint_x,
                                "token_b": mint_y,
                                "price": price,
                                "liquidity_usd": liquidity,
                                "fee_bps": fee_bps,
                                "fee_pct": fee_pct,
                                "pool_type": "DLMM",
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing Meteora pool: {e}")
                        continue
    else:
        logger.warning("Meteora: All retry attempts failed")
    
    logger.info(f"Fetched {len(pools)} Meteora DLMM pools")
    return pools


# ============================================================================
# LIFINITY v2
# ============================================================================

async def fetch_lifinity_pools(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Récupère toutes les pools Lifinity v2.
    
    Endpoint: https://lifinity.io/api/getPools
    
    Returns:
        Liste de pools avec: pool_id, tokenA, tokenB, price, liquidity, fee
    """
    url = "https://lifinity.io/api/getPools"
    pools = []
    
    data = await fetch_with_retry(session, url, "Lifinity", timeout=15)
    if data:
        pools_data = data if isinstance(data, list) else data.get("pools", [])
        
        for pool in pools_data:
                    try:
                        pool_id = pool.get("poolId") or pool.get("address") or pool.get("id")
                        token_a = pool.get("tokenAMint") or pool.get("tokenA")
                        token_b = pool.get("tokenBMint") or pool.get("tokenB")
                        
                        # Prix peut être direct
                        price = pool.get("price")
                        if price:
                            price = float(price)
                        else:
                            # Calcul depuis reserves
                            reserve_a = pool.get("reserveA")
                            reserve_b = pool.get("reserveB")
                            if reserve_a and reserve_b and float(reserve_a) > 0:
                                price = float(reserve_b) / float(reserve_a)
                        
                        liquidity = float(pool.get("liquidity", 0) or pool.get("tvl", 0) or 0)
                        
                        # Fee en pourcentage ou bps
                        fee = pool.get("fee") or pool.get("feeRate") or 0.002  # Default 0.2%
                        if isinstance(fee, str):
                            fee = float(fee)
                        
                        if fee < 1:  # Probablement en pourcentage
                            fee_bps = int(fee * 10000)
                        else:
                            fee_bps = int(fee)
                        
                        fee_pct = fee_bps / 10000.0
                        
                        if pool_id and token_a and token_b:
                            pools.append({
                                "pool_id": pool_id,
                                "dex": "lifinity",
                                "token_a": token_a,
                                "token_b": token_b,
                                "price": price,
                                "liquidity_usd": liquidity,
                                "fee_bps": fee_bps,
                                "fee_pct": fee_pct,
                                "pool_type": "PMM",
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing Lifinity pool: {e}")
                        continue
    else:
        logger.warning("Lifinity: All retry attempts failed")
    
    logger.info(f"Fetched {len(pools)} Lifinity pools")
    return pools


# ============================================================================
# PHOENIX AMM (optionnel)
# ============================================================================

async def fetch_phoenix_pools(session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Récupère les markets Phoenix (order book, mais on peut extraire des infos).
    
    Endpoint: https://api.phoenix.so/v1/markets
    
    Returns:
        Liste de pools avec: pool_id, base_mint, quote_mint, mid_price
    """
    url = PHOENIX_MARKETS_API
    pools = []
    
    markets = await fetch_with_retry(session, url, "Phoenix", timeout=10)
    if markets:
        # markets est déjà une liste ou dict
        markets_list = markets if isinstance(markets, list) else []
        
        for market in markets_list:
                    try:
                        pool_id = market.get("address") or market.get("marketId")
                        base_mint = market.get("baseMint")
                        quote_mint = market.get("quoteMint")
                        mid_price = market.get("midPrice") or market.get("price")
                        
                        if pool_id and base_mint and quote_mint and mid_price:
                            price = float(mid_price)
                            liquidity = float(market.get("liquidity", 0) or 0)
                            
                            # Phoenix a des frais très faibles (0.04%)
                            fee_bps = 4  # 0.04%
                            fee_pct = 0.0004
                            
                            pools.append({
                                "pool_id": pool_id,
                                "dex": "phoenix",
                                "token_a": base_mint,
                                "token_b": quote_mint,
                                "price": price,
                                "liquidity_usd": liquidity,
                                "fee_bps": fee_bps,
                                "fee_pct": fee_pct,
                                "pool_type": "OrderBook",
                            })
                    except Exception as e:
                        logger.debug(f"Error parsing Phoenix market: {e}")
                        continue
    else:
        logger.debug("Phoenix: All retry attempts failed")
    
    logger.info(f"Fetched {len(pools)} Phoenix markets")
    return pools


# ============================================================================
# FONCTION PRINCIPALE: FETCH ALL POOLS
# ============================================================================

async def fetch_all_pools(session: aiohttp.ClientSession, use_cache: bool = True) -> Dict[str, List[Dict[str, Any]]]:
    """
    Récupère toutes les pools de tous les DEX en parallèle avec cache.
    
    Args:
        session: aiohttp session
        use_cache: Si True, utilise le cache si valide (TTL 30s)
    
    Returns:
        {
            "raydium": [...],
            "orca": [...],
            "meteora": [...],
            "lifinity": [...],
            "phoenix": [...]
        }
    """
    global _pools_cache, _cache_timestamp
    
    # Vérifier le cache
    current_time = time.time()
    if use_cache and _pools_cache is not None and (current_time - _cache_timestamp) < CACHE_TTL_SECONDS:
        cache_age = current_time - _cache_timestamp
        logger.debug(f"Using cached pools (age: {cache_age:.1f}s)")
        return _pools_cache
    
    logger.info("Fetching all pools from DEX...")
    
    # Récupérer toutes les pools en parallèle
    raydium, orca, meteora, lifinity, phoenix = await asyncio.gather(
        fetch_raydium_pools(session),
        fetch_orca_whirlpools(session),
        fetch_meteora_pools(session),
        fetch_lifinity_pools(session),
        fetch_phoenix_pools(session),
        return_exceptions=True
    )
    
    # Gérer les exceptions
    if isinstance(raydium, Exception):
        logger.error(f"Raydium fetch error: {raydium}")
        raydium = []
    if isinstance(orca, Exception):
        logger.error(f"Orca fetch error: {orca}")
        orca = []
    if isinstance(meteora, Exception):
        logger.error(f"Meteora fetch error: {meteora}")
        meteora = []
    if isinstance(lifinity, Exception):
        logger.error(f"Lifinity fetch error: {lifinity}")
        lifinity = []
    if isinstance(phoenix, Exception):
        logger.debug(f"Phoenix fetch error: {phoenix}")
        phoenix = []
    
    total = len(raydium) + len(orca) + len(meteora) + len(lifinity) + len(phoenix)
    logger.info(f"Total pools fetched: {total} (Raydium: {len(raydium)}, Orca: {len(orca)}, Meteora: {len(meteora)}, Lifinity: {len(lifinity)}, Phoenix: {len(phoenix)})")
    
    # Mettre en cache
    result = {
        "raydium": raydium,
        "orca": orca,
        "meteora": meteora,
        "lifinity": lifinity,
        "phoenix": phoenix,
    }
    
    _pools_cache = result
    _cache_timestamp = current_time
    
    return result


# ============================================================================
# HELPERS: THEGRAPH GENERIC QUERY
# ============================================================================

async def query_thegraph_pools(
    session: aiohttp.ClientSession,
    tokens: List[str],
    subgraph_url: str
) -> List[Dict[str, Any]]:
    """
    Interroge un subgraph TheGraph pour récupérer les pools contenant les tokens donnés.
    """
    pools: List[Dict[str, Any]] = []
    chunk_size = 10
    headers = {"Content-Type": "application/json"}

    async def post_graph(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(
                    subgraph_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=20),
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 429:
                        wait = INITIAL_RETRY_DELAY * (2 ** attempt) + 1
                        logger.warning(f"[thegraph] 429 on {subgraph_url}, retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(f"[thegraph] status {resp.status} on {subgraph_url}")
            except Exception as e:
                logger.warning(f"[thegraph] error {e} (attempt {attempt+1}/{MAX_RETRIES})")
            await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))
        return None

    for i in range(0, len(tokens), chunk_size):
        chunk = tokens[i:i+chunk_size]
        query = """
        query Pools($tokens: [Bytes!]!) {
          pools(where: {token0_in: $tokens, token1_in: $tokens}, first: 1000) {
            id
            token0 { id decimals }
            token1 { id decimals }
            feeTier
            sqrtPrice
            liquidity
            totalValueLockedUSD
          }
        }
        """
        payload = {"query": query, "variables": {"tokens": chunk}}
        data = await post_graph(payload)
        if not data:
            continue
        try:
            pools_data = data.get("data", {}).get("pools", [])
            pools.extend(pools_data)
        except Exception as e:
            logger.debug(f"[thegraph] parse error: {e}")
            continue
    return pools


# ============================================================================
# HELPERS: POOLS APLATIES PAR TOKEN (SOLANA / BASE)

async def fetch_solana_pools(tokens: List[str], session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Retourne toutes les pools SOLANA contenant les tokens demandés,
    sous forme aplatie avec prix buy/sell, URLs et métadonnées.
    """
    from pool_prices import get_pool_prices_for_token  # import retardé pour éviter les cycles

    all_pools = await fetch_all_pools(session, use_cache=True)
    results: List[Dict[str, Any]] = []

    for token in tokens:
        try:
            token_pools = await get_pool_prices_for_token(
                session=session,
                token_mint=token,
                base_mint=SOL_MINT,
                all_pools=all_pools
            )
            for p in token_pools:
                enriched = dict(p)
                enriched["token"] = token
                enriched["chain"] = "solana"
                results.append(enriched)
        except Exception as e:
            logger.error(f"[fetch_solana_pools] Error for token {token[:8]}: {e}")
            continue

    logger.info(f"[fetch_solana_pools] Total pools flatten: {len(results)}")
    return results


async def fetch_base_pools(tokens: List[str], session: aiohttp.ClientSession) -> List[Dict[str, Any]]:
    """
    Récupère les pools sur Base (cascade: subgraphs → APIs → statique).
    Retourne une liste aplatie de pools normalisées.
    """
    now = time.time()
    if now - _base_cache.get("timestamp", 0) < CACHE_TTL_SECONDS:
        logger.debug("[fetch_base_pools] Using Base cache")
        return list(_base_cache.get("data", []))

    MIN_LIQ_USD = 100.0
    results: List[Dict[str, Any]] = []
    seen = set()

    async def fetch_with_backoff(url: str, dex_name: str, timeout: int = 10) -> Optional[Dict[str, Any]]:
        if _dex_down_until.get(dex_name, 0) > time.time():
            logger.debug(f"[{dex_name}] skipped (down TTL)")
            return None

        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == 200:
                        return await resp.json()
                    if resp.status == 429:
                        wait = INITIAL_RETRY_DELAY * (2 ** attempt) + 1
                        logger.warning(f"[{dex_name}] 429 rate limit, retry in {wait}s")
                        await asyncio.sleep(wait)
                        continue
                    logger.warning(f"[{dex_name}] status {resp.status} on {url}")
            except Exception as e:
                logger.warning(f"[{dex_name}] error {e} (attempt {attempt+1}/{MAX_RETRIES})")
            await asyncio.sleep(INITIAL_RETRY_DELAY * (2 ** attempt))

        _dex_down_until[dex_name] = time.time() + DEX_DOWN_TTL_SECONDS
        return None

    async def fetch_kyber_for_token(token: str) -> List[Dict[str, Any]]:
        pools: List[Dict[str, Any]] = []
        base_url = KYBERSWAP_BASE_API
        urls = [
            base_url.format(token=token),
            base_url.replace("token0", "token1").format(token=token),
        ]
        for url in urls:
            data = await fetch_with_backoff(url, "kyber")
            if not data:
                continue
            items = data.get("data", {}).get("pools", []) if isinstance(data, dict) else []
            for p in items:
                try:
                    pid = p.get("address") or p.get("id")
                    token0 = p.get("token0", {})
                    token1 = p.get("token1", {})
                    dec0 = int(token0.get("decimals", 18))
                    dec1 = int(token1.get("decimals", 18))
                    sqrt_px = float(p.get("sqrtPriceX96") or 0)
                    price = sqrt_price_x96_to_price(sqrt_px, dec0, dec1)
                    fee_bps = int(p.get("feeTier", 0) or 3000)
                    if not pid or not price or price <= 0:
                        continue
                    liq_usd = float(p.get("tvlUsd", 0) or 0)
                    if liq_usd < MIN_LIQ_USD:
                        continue
                    token0_addr = token0.get("address")
                    token1_addr = token1.get("address")
                    fee_pct = max(0.0, min(fee_bps / 10000.0, 0.05))
                    buy_price = price if token == token1_addr else 1 / price
                    sell_price = 1 / price if token == token1_addr else price
                    key = f"{pid}-kyber-{token}"
                    if key in seen:
                        continue
                    seen.add(key)
                    pools.append({
                        "token": token if token == token0_addr or token == token1_addr else token0_addr,
                        "pool_id": pid,
                        "dex": "kyber",
                        "buy_price": buy_price,
                        "sell_price": sell_price,
                        "fee_pct": fee_pct,
                        "liquidity_usd": max(liq_usd, 0.0),
                        "url": f"https://kyberswap.com/elastic/pool/{pid}?chainId=8453",
                        "chain": "base",
                    })
                except Exception as e:
                    logger.debug(f"[kyber] parse error: {e}")
                    continue
        return pools

    async def fetch_aerodrome_for_token(token: str) -> List[Dict[str, Any]]:
        pools: List[Dict[str, Any]] = []
        url = AERODROME_POOLS_API
        data = await fetch_with_backoff(url, "aerodrome", timeout=15)
        if not data:
            return pools
        items = data.get("data", []) if isinstance(data, dict) else data if isinstance(data, list) else []
        for p in items:
            try:
                pid = p.get("address") or p.get("id")
                t0 = p.get("token0", {})
                t1 = p.get("token1", {})
                token0 = t0.get("address")
                token1 = t1.get("address")
                if token0 != token and token1 != token:
                    continue
                price = None
                reserve0 = float(p.get("reserve0", 0) or 0)
                reserve1 = float(p.get("reserve1", 0) or 0)
                if reserve0 > 0 and reserve1 > 0:
                    price = reserve1 / reserve0
                if not pid or not price or price <= 0:
                    continue
                fee_raw = float(p.get("fee", 0) or 0)
                fee_bps = int(fee_raw * 10000) if fee_raw < 1 else int(fee_raw)
                fee_pct = max(0.0, min(fee_bps / 10000.0, 0.05))
                tvl = float(p.get("tvlUsd", 0) or p.get("liquidityUsd", 0) or 0)
                if tvl < MIN_LIQ_USD:
                    continue
                buy_price = price if token == token0 else 1 / price
                sell_price = 1 / price if token == token0 else price
                key = f"{pid}-aerodrome-{token}"
                if key in seen:
                    continue
                seen.add(key)
                pools.append({
                    "token": token,
                    "pool_id": pid,
                    "dex": "aerodrome",
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "fee_pct": fee_pct,
                    "liquidity_usd": max(tvl, 0.0),
                    "url": f"https://aerodrome.finance/pools/{pid}",
                    "chain": "base",
                })
            except Exception as e:
                logger.debug(f"[aerodrome] parse error: {e}")
                continue
        return pools

    for token in tokens:
        token_results: List[Dict[str, Any]] = []

        # Niveau 1 : subgraphs (Uniswap / Pancake)
        uni_pool = await get_pool_from_subgraph(session, token, BASE_USDC, "uniswap_v3", "base")
        if uni_pool and uni_pool.get("liquidity_usd", 0) >= MIN_LIQ_USD:
            token_results.append(uni_pool)

        cake_pool = await get_pool_from_subgraph(session, token, BASE_USDC, "pancake_v3", "base")
        if cake_pool and cake_pool.get("liquidity_usd", 0) >= MIN_LIQ_USD:
            token_results.append(cake_pool)

        # Niveau 2 : APIs directes si rien
        if not token_results:
            token_results.extend(await fetch_kyber_for_token(token))
            token_results.extend(await fetch_aerodrome_for_token(token))

        # Niveau 3 : fallback statique
        if not token_results:
            static_pools = get_static_pools_for_pair(token, BASE_USDC, "base")
            token_results.extend(static_pools)
            if static_pools:
                logger.info(f"[fetch_base_pools] using static pools for {token[:8]}...")

        if not token_results:
            logger.warning(f"[fetch_base_pools] No pools for token {token[:8]}...")
        results.extend(token_results)

    _base_cache["timestamp"] = now
    _base_cache["data"] = list(results)

    counts = {}
    for p in results:
        counts[p.get("dex")] = counts.get(p.get("dex"), 0) + 1
    logger.info(f"[fetch_base_pools] counts_by_dex={counts} total={len(results)}")

    if not results:
        logger.warning(json.dumps({
            "event": "fetch_base_pools_empty",
            "tokens": tokens,
            "timestamp": time.time()
        }))

    return results

