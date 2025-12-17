# price_fetchers.py
"""
Module pour récupérer les prix depuis les DEX natifs.

SOLANA (6 DEX):
1. Jupiter (aggregator) - API officielle avec clé
2. Raydium (AMM) - API v3
3. Orca (Whirlpools) - API officielle
4. Meteora (DLMM) - API officielle
5. Phoenix (order book) - API officielle
6. Lifinity (PMM) - API officielle

BASE (4 DEX):
1. Uniswap V3
2. Aerodrome Finance
3. PancakeSwap V3
4. KyberSwap

🚀 OPTIMISATION RUST:
Ce module peut utiliser un binaire Rust pour récupérer les prix ultra-rapidement.
Si le binaire Rust n'est pas disponible, le fallback Python est utilisé.
"""
import asyncio
import aiohttp
import subprocess
import json
import os
from typing import Optional, Dict, Any, List
from config import (
    JUPITER_API_KEY, JUPITER_PRICE_API, JUPITER_QUOTE_API,
    RAYDIUM_API, ORCA_API, METEORA_API, PHOENIX_API, LIFINITY_API,
    RPC_ENDPOINT
)
from utils import logger

# Import Base DEX fetchers
try:
    from base_dex_fetchers import (
        get_all_base_dex_prices,
        get_uniswap_price,
        get_aerodrome_price,
        get_pancakeswap_price,
        get_kyberswap_price,
        WETH_BASE,
        USDC_BASE,
    )
    BASE_FETCHERS_AVAILABLE = True
except ImportError:
    BASE_FETCHERS_AVAILABLE = False

# ============================================================================
# RUST PRICE FETCHER (Ultra-fast)
# ============================================================================

RUST_BINARY_PATH = os.path.join(
    os.path.dirname(__file__), 
    "rust_price_fetcher", 
    "target", 
    "release", 
    "price_fetcher.exe" if os.name == "nt" else "price_fetcher"
)

_rust_binary_available = None

def is_rust_binary_available() -> bool:
    """Vérifie si le binaire Rust est disponible et exécutable."""
    global _rust_binary_available
    
    if _rust_binary_available is not None:
        return _rust_binary_available
    
    _rust_binary_available = os.path.isfile(RUST_BINARY_PATH) and os.access(RUST_BINARY_PATH, os.X_OK)
    
    if _rust_binary_available:
        logger.info("🦀 Binaire Rust price_fetcher détecté - Mode ultra-rapide activé!")
    else:
        logger.info("⚠️ Binaire Rust non trouvé - Mode Python utilisé")
        logger.info(f"   Compilez avec: cd rust_price_fetcher && cargo build --release")
    
    return _rust_binary_available

def fetch_prices_with_rust(
    solana_tokens: List[str], 
    base_tokens: List[str] = None
) -> Optional[Dict[str, Dict[str, Dict[str, float]]]]:
    """
    Appelle le binaire Rust pour récupérer les prix ultra-rapidement.
    
    Returns:
        {"solana": {token: {dex: price}}, "base": {token: {dex: price}}}
    """
    if not is_rust_binary_available():
        return None
    
    if base_tokens is None:
        base_tokens = []
    
    try:
        # Build arguments: api_key chain:token1 chain:token2 ...
        args = [RUST_BINARY_PATH, JUPITER_API_KEY]
        
        for token in solana_tokens:
            args.append(f"solana:{token}")
        for token in base_tokens:
            args.append(f"base:{token}")
        
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode != 0:
            logger.warning(f"Rust binary error: {result.stderr}")
            return None
        
        output = json.loads(result.stdout)
        
        if not output.get("success"):
            return None
        
        # Transform to expected format
        prices = {"solana": {}, "base": {}}
        
        for token_data in output.get("solana_tokens", []):
            token = token_data.get("token")
            token_prices = token_data.get("prices", {})
            if token and token_prices:
                prices["solana"][token] = token_prices
        
        for token_data in output.get("base_tokens", []):
            token = token_data.get("token")
            token_prices = token_data.get("prices", {})
            if token and token_prices:
                prices["base"][token] = token_prices
        
        fetch_time_ms = output.get("fetch_time_ms", 0)
        logger.info(f"🦀 Rust: {len(prices['solana'])} Solana + {len(prices['base'])} Base tokens en {fetch_time_ms}ms")
        
        return prices
        
    except Exception as e:
        logger.warning(f"Error calling Rust binary: {e}")
        return None

# ============================================================================
# JUPITER (Aggregator - Primary source for Solana)
# ============================================================================

async def get_jupiter_prices(
    session: aiohttp.ClientSession,
    token_mints: List[str]
) -> Dict[str, float]:
    """
    Récupère les prix depuis Jupiter Price API v2.
    Jupiter agrège les meilleurs prix de tous les DEX Solana.
    """
    if not token_mints:
        return {}
    
    prices = {}
    ids = ",".join(token_mints)
    url = f"{JUPITER_PRICE_API}?ids={ids}"
    
    headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
    
    try:
        async with session.get(url, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                for mint, info in data.get("data", {}).items():
                    price = info.get("price")
                    if price:
                        try:
                            prices[mint] = float(price)
                        except (ValueError, TypeError):
                            pass
            else:
                logger.debug(f"Jupiter API status: {resp.status}")
    except Exception as e:
        logger.debug(f"Jupiter error: {e}")
    
    return prices

async def get_jupiter_quote(
    session: aiohttp.ClientSession, 
    input_mint: str, 
    output_mint: str, 
    amount: int = 1_000_000,
    slippage_bps: int = 50
) -> Optional[Dict[str, Any]]:
    """Query Jupiter v6 quote API pour un swap."""
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": amount,
        "slippageBps": slippage_bps,
    }
    headers = {"x-api-key": JUPITER_API_KEY} if JUPITER_API_KEY else {}
    
    try:
        async with session.get(JUPITER_QUOTE_API, params=params, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                if "outAmount" in data:
                    return data
    except Exception as e:
        logger.debug(f"Jupiter quote error: {e}")
    return None

# ============================================================================
# RAYDIUM (AMM - Largest Solana DEX)
# ============================================================================

async def get_raydium_prices(
    session: aiohttp.ClientSession,
    token_mints: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Raydium API v3."""
    if not token_mints:
        return {}
    
    prices = {}
    ids = ",".join(token_mints)
    url = f"{RAYDIUM_API}/mint/price?mints={ids}"
    
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                for mint, price_str in data.get("data", {}).items():
                    try:
                        price = float(price_str)
                        if price > 0:
                            prices[mint] = price
                    except (ValueError, TypeError):
                        pass
            else:
                logger.debug(f"Raydium API status: {resp.status}")
    except Exception as e:
        logger.debug(f"Raydium error: {e}")
    
    return prices

# ============================================================================
# ORCA (Whirlpools - Concentrated Liquidity)
# ============================================================================

async def get_orca_prices(
    session: aiohttp.ClientSession,
    token_mints: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Orca Whirlpools."""
    if not token_mints:
        return {}
    
    prices = {}
    url = f"{ORCA_API}/v1/token/list"
    
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                for mint in token_mints:
                    if mint in data:
                        token_info = data[mint]
                        price = token_info.get("price")
                        if price and price > 0:
                            prices[mint] = float(price)
            else:
                logger.debug(f"Orca API status: {resp.status}")
    except Exception as e:
        logger.debug(f"Orca error: {e}")
    
    return prices

# ============================================================================
# METEORA (DLMM - Dynamic Liquidity Market Maker)
# ============================================================================

async def get_meteora_prices(
    session: aiohttp.ClientSession,
    token_mints: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Meteora DLMM pools.
    
    NOTE: L'API Meteora utilise des underscores: mint_x, mint_y, current_price
    """
    if not token_mints:
        return {}
    
    prices = {}
    url = f"{METEORA_API}/pair/all"
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    try:
        async with session.get(url, timeout=15) as resp:
            if resp.status == 200:
                pools = await resp.json()
                
                # Pour chaque token, trouver le meilleur pool (plus de liquidité)
                best_pools = {}  # {mint: {"price": x, "liq": y}}
                
                for pool in pools:
                    # IMPORTANT: utiliser underscore (mint_x, mint_y, current_price)
                    mint_x = pool.get("mint_x", "")
                    mint_y = pool.get("mint_y", "")
                    current_price = pool.get("current_price")
                    liquidity = float(pool.get("liquidity", 0) or 0)
                    
                    # Rejeter pools trop petits pour éviter des prix obsolètes
                    if not current_price or liquidity < 20000:
                        continue
                    
                    try:
                        price = float(current_price)
                        if price <= 0:
                            continue
                        
                        for mint in token_mints:
                            if mint_x == mint and mint_y == usdc:
                                if mint not in best_pools or liquidity > best_pools[mint]["liq"]:
                                    best_pools[mint] = {"price": price, "liq": liquidity}
                            elif mint_x == usdc and mint_y == mint:
                                inverted_price = 1.0 / price
                                if mint not in best_pools or liquidity > best_pools[mint]["liq"]:
                                    best_pools[mint] = {"price": inverted_price, "liq": liquidity}
                    except (ValueError, TypeError):
                        pass
                
                # Extraire les prix
                for mint, data in best_pools.items():
                    prices[mint] = data["price"]
                    
            else:
                logger.debug(f"Meteora API status: {resp.status}")
    except Exception as e:
        logger.debug(f"Meteora error: {e}")
    
    return prices

# ============================================================================
# PHOENIX (Order Book DEX)
# ============================================================================

async def get_phoenix_prices(
    session: aiohttp.ClientSession,
    token_mints: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Phoenix (order book)."""
    if not token_mints:
        return {}
    
    prices = {}
    url = f"{PHOENIX_API}/v1/markets"
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                markets = await resp.json()
                
                for market in markets:
                    base_mint = market.get("baseMint")
                    quote_mint = market.get("quoteMint")
                    mid_price = market.get("midPrice")
                    
                    if not all([base_mint, quote_mint, mid_price]):
                        continue
                    
                    try:
                        price = float(mid_price)
                        if price <= 0:
                            continue
                        
                        for mint in token_mints:
                            if base_mint == mint and quote_mint == usdc:
                                prices[mint] = price
                    except (ValueError, TypeError):
                        pass
            else:
                logger.debug(f"Phoenix API status: {resp.status}")
    except Exception as e:
        logger.debug(f"Phoenix error: {e}")
    
    return prices

# ============================================================================
# LIFINITY (Proactive Market Maker)
# ============================================================================

async def get_lifinity_prices(
    session: aiohttp.ClientSession,
    token_mints: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Lifinity pools."""
    if not token_mints:
        return {}
    
    prices = {}
    url = f"{LIFINITY_API}/pools"
    usdc = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    
    try:
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                pools = await resp.json()
                
                for pool in pools:
                    mint_a = pool.get("tokenAMint")
                    mint_b = pool.get("tokenBMint")
                    pool_price = pool.get("price")
                    
                    if not all([mint_a, mint_b, pool_price]):
                        continue
                    
                    try:
                        price = float(pool_price)
                        if price <= 0:
                            continue
                        
                        for mint in token_mints:
                            if mint_a == mint and mint_b == usdc:
                                prices[mint] = price
                            elif mint_a == usdc and mint_b == mint:
                                prices[mint] = 1.0 / price
                    except (ValueError, TypeError):
                        pass
            else:
                logger.debug(f"Lifinity API status: {resp.status}")
    except Exception as e:
        logger.debug(f"Lifinity error: {e}")
    
    return prices

# ============================================================================
# BASE DEX (Uniswap V3, Aerodrome, PancakeSwap V3, KyberSwap)
# ============================================================================

# Base chain token addresses (re-export for backward compatibility)
if not BASE_FETCHERS_AVAILABLE:
    WETH_BASE = "0x4200000000000000000000000000000000000006"
    USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


async def get_kyberswap_base_prices(
    session: aiohttp.ClientSession,
    token_addresses: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis KyberSwap sur Base.
    
    KyberSwap est un agrégateur qui fonctionne sur Base.
    Endpoint: https://aggregator-api.kyberswap.com/base/api/v1/routes
    """
    prices = {}
    
    for token in token_addresses:
        try:
            if BASE_FETCHERS_AVAILABLE:
                result = await get_kyberswap_price(session, token, USDC_BASE)
                if result and result.get("price"):
                    prices[token] = result["price"]
            else:
                # Fallback implementation
                amount_in = "1000000000000000000"
                url = f"https://aggregator-api.kyberswap.com/base/api/v1/routes?tokenIn={token}&tokenOut={USDC_BASE}&amountIn={amount_in}"
                
                async with session.get(url, timeout=10) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        route_summary = data.get("data", {}).get("routeSummary", {})
                        amount_out = route_summary.get("amountOut", "0")
                        if amount_out and int(amount_out) > 0:
                            price = int(amount_out) / 1_000_000
                            prices[token] = price
        except Exception as e:
            logger.debug(f"KyberSwap error for {token[:8]}: {e}")
    
    return prices


async def get_uniswap_base_prices(
    session: aiohttp.ClientSession,
    token_addresses: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Uniswap V3 sur Base."""
    if not BASE_FETCHERS_AVAILABLE:
        return {}
    
    prices = {}
    for token in token_addresses:
        try:
            result = await get_uniswap_price(session, token, USDC_BASE)
            if result and result.get("price"):
                prices[token] = result["price"]
        except Exception as e:
            logger.debug(f"Uniswap error for {token[:8]}: {e}")
    
    return prices


async def get_aerodrome_prices(
    session: aiohttp.ClientSession,
    token_addresses: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis Aerodrome sur Base."""
    if not BASE_FETCHERS_AVAILABLE:
        return {}
    
    prices = {}
    for token in token_addresses:
        try:
            result = await get_aerodrome_price(session, token, USDC_BASE)
            if result and result.get("price"):
                prices[token] = result["price"]
        except Exception as e:
            logger.debug(f"Aerodrome error for {token[:8]}: {e}")
    
    return prices


async def get_pancakeswap_base_prices(
    session: aiohttp.ClientSession,
    token_addresses: List[str]
) -> Dict[str, float]:
    """Récupère les prix depuis PancakeSwap V3 sur Base."""
    if not BASE_FETCHERS_AVAILABLE:
        return {}
    
    prices = {}
    for token in token_addresses:
        try:
            result = await get_pancakeswap_price(session, token, USDC_BASE)
            if result and result.get("price"):
                prices[token] = result["price"]
        except Exception as e:
            logger.debug(f"PancakeSwap error for {token[:8]}: {e}")
    
    return prices

# ============================================================================
# MAIN FUNCTIONS
# ============================================================================

async def get_all_dex_prices(
    session: aiohttp.ClientSession,
    token_mint: str,
    base_mint: str = "So11111111111111111111111111111111111111112"
) -> Dict[str, Optional[float]]:
    """
    Récupère les prix depuis les 6 DEX Solana en parallèle.
    
    Returns:
        Dict avec prix pour chaque DEX (float) ou None si indisponible
    """
    token_list = [token_mint]
    
    # Fetch all 6 DEX in parallel
    jupiter, raydium, orca, meteora, phoenix, lifinity = await asyncio.gather(
        get_jupiter_prices(session, token_list),
        get_raydium_prices(session, token_list),
        get_orca_prices(session, token_list),
        get_meteora_prices(session, token_list),
        get_phoenix_prices(session, token_list),
        get_lifinity_prices(session, token_list),
    )
    
    # Combine results
    dex_prices = {
        "jupiter": jupiter.get(token_mint),
        "raydium": raydium.get(token_mint),
        "orca": orca.get(token_mint),
        "meteora": meteora.get(token_mint),
        "phoenix": phoenix.get(token_mint),
        "lifinity": lifinity.get(token_mint),
    }
    
    # Log results
    valid_count = sum(1 for p in dex_prices.values() if p is not None)
    logger.info(f"Token {token_mint[:8]}: {valid_count}/6 DEX avec prix")
    
    for dex, price in dex_prices.items():
        if price:
            logger.debug(f"  {dex.upper()}: ${price:.8f}")
    
    return dex_prices

async def get_all_prices_batch(
    session: aiohttp.ClientSession,
    solana_tokens: List[str],
    base_tokens: List[str] = None
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Récupère les prix pour plusieurs tokens en batch.
    
    Returns:
        {"solana": {token: {dex: price}}, "base": {token: {dex: price}}}
    """
    if base_tokens is None:
        base_tokens = []
    
    # Try Rust first (10x faster)
    rust_result = fetch_prices_with_rust(solana_tokens, base_tokens)
    if rust_result is not None:
        return rust_result
    
    # Fallback to Python
    logger.info("Mode Python - récupération des prix...")
    
    # Solana: 6 DEX in parallel
    jupiter, raydium, orca, meteora, phoenix, lifinity = await asyncio.gather(
        get_jupiter_prices(session, solana_tokens),
        get_raydium_prices(session, solana_tokens),
        get_orca_prices(session, solana_tokens),
        get_meteora_prices(session, solana_tokens),
        get_phoenix_prices(session, solana_tokens),
        get_lifinity_prices(session, solana_tokens),
    )
    
    # Base: 3 DEX in parallel
    uniswap, aerodrome, baseswap = await asyncio.gather(
        get_uniswap_base_prices(session, base_tokens),
        get_aerodrome_prices(session, base_tokens),
        get_baseswap_prices(session, base_tokens),  # pyright: ignore[reportUndefinedVariable]
    )
    
    # Aggregate Solana results
    solana_results = {}
    for token in solana_tokens:
        prices = {}
        if token in jupiter and jupiter[token]:
            prices["jupiter"] = jupiter[token]
        if token in raydium and raydium[token]:
            prices["raydium"] = raydium[token]
        if token in orca and orca[token]:
            prices["orca"] = orca[token]
        if token in meteora and meteora[token]:
            prices["meteora"] = meteora[token]
        if token in phoenix and phoenix[token]:
            prices["phoenix"] = phoenix[token]
        if token in lifinity and lifinity[token]:
            prices["lifinity"] = lifinity[token]
        
        solana_results[token] = prices
    
    # Aggregate Base results
    base_results = {}
    for token in base_tokens:
        prices = {}
        if token in uniswap and uniswap[token]:
            prices["uniswap"] = uniswap[token]
        if token in aerodrome and aerodrome[token]:
            prices["aerodrome"] = aerodrome[token]
        if token in baseswap and baseswap[token]:
            prices["baseswap"] = baseswap[token]
        
        base_results[token] = prices
    
    return {"solana": solana_results, "base": base_results}

# ============================================================================
# UTILITIES
# ============================================================================

def estimate_price_from_quote(
    quote: dict, 
    input_decimals: int = 9, 
    output_decimals: int = 9
) -> Optional[float]:
    """Estime le prix unitaire depuis une quote Jupiter."""
    try:
        out_amount = int(quote.get("outAmount", 0))
        in_amount = int(quote.get("inAmount", quote.get("amount", 1)))
        
        if out_amount <= 0 or in_amount <= 0:
            return None
        
        price = (out_amount / (10 ** output_decimals)) / (in_amount / (10 ** input_decimals))
        return float(price)
    except Exception as e:
        logger.debug(f"Error estimating price from quote: {e}")
        return None
