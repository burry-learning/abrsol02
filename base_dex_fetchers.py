# base_dex_fetchers.py
"""
Base Chain DEX Price Fetchers

This module implements price fetching for BASE chain DEX:
- Uniswap V3
- Aerodrome Finance
- PancakeSwap V3
- KyberSwap (already in price_fetchers.py, imported here)

Each function returns structured quote data including:
- output amount
- price
- fee tier
- price impact
- liquidity
"""
import asyncio
import aiohttp
from typing import Dict, Optional, Any
from utils import logger


# =============================================================================
# BASE CHAIN CONSTANTS
# =============================================================================

# Common Base tokens
WETH_BASE = "0x4200000000000000000000000000000000000006"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
USDT_BASE = "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2"

# Base chain ID
BASE_CHAIN_ID = 8453

# Default amounts (1 token with 18 decimals)
DEFAULT_AMOUNT_18 = "1000000000000000000"
DEFAULT_AMOUNT_6 = "1000000"


# =============================================================================
# DEX FEE TABLE FOR BASE
# =============================================================================

BASE_DEX_FEES = {
    "uniswap": 0.003,      # 0.30% default, but use endpoint fee when available
    "aerodrome": 0.0004,   # 0.04% (very low, ve(3,3) model)
    "pancakeswap": 0.0025, # 0.25% default, but use endpoint fee when available
    "kyberswap": 0.0010,   # 0.10%
}

# Fee tiers for Uniswap/Pancake
FEE_TIERS = {
    100: 0.0001,    # 0.01%
    500: 0.0005,    # 0.05%
    3000: 0.003,    # 0.30%
    10000: 0.01,    # 1.00%
}


# =============================================================================
# BASE SLIPPAGE ESTIMATION
# =============================================================================

def estimate_base_slippage(liquidity_usd: float) -> float:
    """
    Estimate slippage for Base chain based on liquidity.
    
    Liquidity tiers:
    - > $1M:      0.05%
    - $200k-1M:   0.10%
    - $20k-200k:  0.25%
    - < $20k:     0.50-1%
    
    Default (no liquidity info): 0.30%
    """
    if liquidity_usd is None or liquidity_usd <= 0:
        return 0.003  # 0.30% default
    
    if liquidity_usd >= 1_000_000:
        return 0.0005  # 0.05%
    elif liquidity_usd >= 200_000:
        return 0.001   # 0.10%
    elif liquidity_usd >= 20_000:
        return 0.0025  # 0.25%
    else:
        return 0.005   # 0.50%


# =============================================================================
# BASE MEV PROTECTION
# =============================================================================

def calculate_base_mev_penalty(liquidity_usd: float) -> float:
    """
    Calculate MEV penalty for Base chain.
    
    Base penalty: 0.15%
    Additional penalty if liquidity < $30k: +0.25%
    """
    base_penalty = 0.0015  # 0.15%
    
    if liquidity_usd is not None and liquidity_usd < 30_000:
        return base_penalty + 0.0025  # 0.40% total
    
    return base_penalty


# =============================================================================
# UNISWAP V3 PRICE FETCHER
# =============================================================================

async def get_uniswap_price(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str = DEFAULT_AMOUNT_18,
    chain: str = "base"
) -> Optional[Dict[str, Any]]:
    """
    Fetch quote from Uniswap V3 on Base.
    
    Uses Uniswap's trading API.
    
    Parameters:
        token_in: Input token address
        token_out: Output token address
        amount: Amount in wei (18 decimals default)
        chain: Chain name (base)
    
    Returns:
        Dict with: output, price, fee_tier, price_impact, liquidity
        None on error
    """
    # Try multiple Uniswap API endpoints
    endpoints = [
        # Uniswap Trading API
        {
            "url": "https://interface.gateway.uniswap.org/v2/quote",
            "method": "POST",
            "body": {
                "tokenInChainId": BASE_CHAIN_ID,
                "tokenOutChainId": BASE_CHAIN_ID,
                "tokenIn": token_in,
                "tokenOut": token_out,
                "amount": str(amount),
                "type": "EXACT_INPUT",
                "configs": [{"routingType": "CLASSIC", "protocols": ["V3"]}]
            }
        },
        # Uniswap Quote API (legacy)
        {
            "url": f"https://api.uniswap.org/v2/quote?tokenInAddress={token_in}&tokenOutAddress={token_out}&tokenInChainId={BASE_CHAIN_ID}&tokenOutChainId={BASE_CHAIN_ID}&amount={amount}&type=exactIn",
            "method": "GET"
        }
    ]
    
    for endpoint in endpoints:
        try:
            headers = {
                "Content-Type": "application/json",
                "Origin": "https://app.uniswap.org",
                "Accept": "application/json"
            }
            
            if endpoint["method"] == "POST":
                async with session.post(
                    endpoint["url"],
                    json=endpoint.get("body"),
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return _parse_uniswap_response(data, token_in, token_out, amount)
            else:
                async with session.get(
                    endpoint["url"],
                    headers=headers,
                    timeout=10
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return _parse_uniswap_response(data, token_in, token_out, amount)
                        
        except asyncio.TimeoutError:
            continue
        except Exception as e:
            logger.debug(f"[BASE] Uniswap endpoint error: {e}")
            continue
    
    # Fallback: try to get price from 1inch API (aggregator that includes Uniswap)
    return await _get_uniswap_via_1inch(session, token_in, token_out, amount)


def _parse_uniswap_response(data: dict, token_in: str, token_out: str, amount: str) -> Optional[Dict[str, Any]]:
    """Parse Uniswap API response."""
    try:
        # Try different response formats
        quote_amount = (
            data.get("quote") or 
            data.get("quoteDecimals") or 
            data.get("outputAmount") or
            "0"
        )
        
        if isinstance(quote_amount, str):
            amount_out = int(float(quote_amount)) if '.' in quote_amount else int(quote_amount)
        else:
            amount_out = int(quote_amount)
        
        if amount_out <= 0:
            return None
        
        # Fee tier
        fee_tier = 3000
        route = data.get("route", [[]])
        if route and len(route) > 0 and len(route[0]) > 0:
            first_hop = route[0][0] if isinstance(route[0][0], dict) else {}
            fee_tier = first_hop.get("fee", 3000)
        
        fee_decimal = FEE_TIERS.get(fee_tier, 0.003)
        
        # Price impact
        price_impact = 0
        if data.get("priceImpact"):
            price_impact = float(data["priceImpact"]) / 100
        
        # Calculate price
        amount_in = int(amount)
        decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
        decimals_in = 18
        
        price = (amount_out / (10 ** decimals_out)) / (amount_in / (10 ** decimals_in))
        
        return {
            "dex": "uniswap",
            "output": amount_out,
            "price": price,
            "fee_tier": fee_tier,
            "fee_decimal": fee_decimal,
            "price_impact": price_impact,
            "liquidity": None,
            "gas_estimate": data.get("gasEstimate"),
        }
    except Exception as e:
        logger.debug(f"[BASE] Uniswap parse error: {e}")
        return None


async def _get_uniswap_via_1inch(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str
) -> Optional[Dict[str, Any]]:
    """Fallback: get Uniswap price via 1inch API."""
    try:
        url = f"https://api.1inch.dev/swap/v6.0/{BASE_CHAIN_ID}/quote"
        params = {
            "src": token_in,
            "dst": token_out,
            "amount": amount,
            "protocols": "UNISWAP_V3"
        }
        headers = {
            "Accept": "application/json"
        }
        
        async with session.get(url, params=params, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                amount_out = int(data.get("toAmount", 0))
                
                if amount_out > 0:
                    amount_in = int(amount)
                    decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
                    price = (amount_out / (10 ** decimals_out)) / (amount_in / (10 ** 18))
                    
                    return {
                        "dex": "uniswap",
                        "output": amount_out,
                        "price": price,
                        "fee_tier": 3000,
                        "fee_decimal": 0.003,
                        "price_impact": None,
                        "liquidity": None,
                    }
    except Exception as e:
        logger.debug(f"[BASE] 1inch fallback error: {e}")
    
    # Final fallback: DeFiLlama
    return await _get_price_via_defillama(session, token_in, "uniswap")


async def _get_price_via_defillama(
    session: aiohttp.ClientSession,
    token: str,
    dex_name: str
) -> Optional[Dict[str, Any]]:
    """Get token price via DeFiLlama API."""
    try:
        # DeFiLlama uses chain:address format
        url = f"https://coins.llama.fi/prices/current/base:{token}"
        
        async with session.get(url, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                coins = data.get("coins", {})
                coin_data = coins.get(f"base:{token}")
                
                if coin_data:
                    price = float(coin_data.get("price", 0))
                    
                    if price > 0:
                        return {
                            "dex": dex_name,
                            "output": 0,
                            "price": price,
                            "fee_tier": 3000 if dex_name == "uniswap" else 2500,
                            "fee_decimal": 0.003 if dex_name == "uniswap" else 0.0025,
                            "price_impact": None,
                            "liquidity": None,
                            "source": "defillama"
                        }
    except Exception as e:
        logger.debug(f"[BASE] DeFiLlama error: {e}")
    
    return None


# =============================================================================
# AERODROME FINANCE PRICE FETCHER
# =============================================================================

async def get_aerodrome_price(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str = DEFAULT_AMOUNT_18
) -> Optional[Dict[str, Any]]:
    """
    Fetch quote from Aerodrome Finance on Base.
    
    Aerodrome uses ve(3,3) model with very low fees.
    Uses multiple fallback methods.
    
    Parameters:
        token_in: Input token address
        token_out: Output token address
        amount: Amount in wei
    
    Returns:
        Dict with: output, price, fee, is_stable, price_impact, liquidity
        None on error
    """
    # Try via OpenOcean aggregator first (includes Aerodrome)
    result = await _get_aerodrome_via_openocean(session, token_in, token_out, amount)
    if result:
        return result
    
    # Try via ParaSwap
    result = await _get_aerodrome_via_paraswap(session, token_in, token_out, amount)
    if result:
        return result
    
    # Fallback: try direct Aerodrome API
    try:
        url = "https://aerodrome.finance/api/v1/quote"
        params = {
            "tokenIn": token_in,
            "tokenOut": token_out,
            "amount": amount,
        }
        
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                return _parse_aerodrome_response(data, token_in, token_out, amount)
                
    except Exception as e:
        logger.debug(f"[BASE] Aerodrome direct API error: {e}")
    
    return None


async def _get_aerodrome_via_openocean(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str
) -> Optional[Dict[str, Any]]:
    """Get Aerodrome price via OpenOcean aggregator."""
    try:
        url = "https://open-api.openocean.finance/v3/base/quote"
        params = {
            "inTokenAddress": token_in,
            "outTokenAddress": token_out,
            "amount": str(int(amount) / (10 ** 18)),  # OpenOcean expects decimal amount
            "gasPrice": "0.001"
        }
        
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                if data.get("code") == 200 and data.get("data"):
                    out_amount = float(data["data"].get("outAmount", 0))
                    
                    if out_amount > 0:
                        in_amount = float(data["data"].get("inAmount", 1))
                        price = out_amount / in_amount if in_amount > 0 else 0
                        
                        return {
                            "dex": "aerodrome",
                            "output": int(out_amount * (10 ** 6)),  # Convert to USDC decimals
                            "price": price,
                            "fee_decimal": 0.0004,  # Aerodrome default
                            "is_stable": False,
                            "price_impact": None,
                            "liquidity": None,
                        }
    except Exception as e:
        logger.debug(f"[BASE] OpenOcean error: {e}")
    
    return None


async def _get_aerodrome_via_paraswap(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str
) -> Optional[Dict[str, Any]]:
    """Get Aerodrome price via ParaSwap aggregator."""
    try:
        url = "https://apiv5.paraswap.io/prices"
        params = {
            "srcToken": token_in,
            "destToken": token_out,
            "amount": amount,
            "srcDecimals": 18,
            "destDecimals": 6 if token_out.lower() == USDC_BASE.lower() else 18,
            "network": BASE_CHAIN_ID,
            "excludeDEXS": ""  # Include all DEXs
        }
        
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                price_route = data.get("priceRoute", {})
                
                dest_amount = int(price_route.get("destAmount", 0))
                if dest_amount > 0:
                    decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
                    amount_in = int(amount)
                    price = (dest_amount / (10 ** decimals_out)) / (amount_in / (10 ** 18))
                    
                    return {
                        "dex": "aerodrome",
                        "output": dest_amount,
                        "price": price,
                        "fee_decimal": 0.0004,
                        "is_stable": False,
                        "price_impact": None,
                        "liquidity": None,
                    }
    except Exception as e:
        logger.debug(f"[BASE] ParaSwap error: {e}")
    
    return None


def _parse_aerodrome_response(data: dict, token_in: str, token_out: str, amount: str) -> Optional[Dict[str, Any]]:
    """Parse Aerodrome API response."""
    try:
        amount_out = int(data.get("amountOut", 0))
        is_stable = data.get("isStable", False)
        fee = float(data.get("fee", 0.04)) / 100 if data.get("fee") else 0.0004
        price_impact = float(data.get("priceImpact", 0)) / 100 if data.get("priceImpact") else None
        liquidity = float(data.get("liquidity", 0)) if data.get("liquidity") else None
        
        if amount_out > 0:
            amount_in = int(amount)
            decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
            price = (amount_out / (10 ** decimals_out)) / (amount_in / (10 ** 18))
            
            return {
                "dex": "aerodrome",
                "output": amount_out,
                "price": price,
                "fee_decimal": fee,
                "is_stable": is_stable,
                "price_impact": price_impact,
                "liquidity": liquidity,
            }
    except Exception as e:
        logger.debug(f"[BASE] Aerodrome parse error: {e}")
    
    return None


# =============================================================================
# PANCAKESWAP V3 PRICE FETCHER
# =============================================================================

async def get_pancakeswap_price(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str = DEFAULT_AMOUNT_18
) -> Optional[Dict[str, Any]]:
    """
    Fetch quote from PancakeSwap V3 on Base.
    
    Uses PancakeSwap's smart router API with fallbacks.
    
    Parameters:
        token_in: Input token address
        token_out: Output token address
        amount: Amount in wei
    
    Returns:
        Dict with: output, price, fee_tier, price_impact, liquidity
        None on error
    """
    # Try PancakeSwap smart router API
    result = await _get_pancake_via_smart_router(session, token_in, token_out, amount)
    if result:
        return result
    
    # Try via 0x API (includes PancakeSwap)
    result = await _get_pancake_via_0x(session, token_in, token_out, amount)
    if result:
        return result
    
    return None


async def _get_pancake_via_smart_router(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str
) -> Optional[Dict[str, Any]]:
    """Try PancakeSwap smart router API."""
    try:
        # PancakeSwap uses a POST endpoint for quotes
        url = "https://routing-api.pancakeswap.com/v1/quote"
        
        payload = {
            "chainId": BASE_CHAIN_ID,
            "amount": str(amount),
            "currencyIn": {
                "address": token_in,
                "chainId": BASE_CHAIN_ID,
                "decimals": 18
            },
            "currencyOut": {
                "address": token_out,
                "chainId": BASE_CHAIN_ID,
                "decimals": 6 if token_out.lower() == USDC_BASE.lower() else 18
            },
            "tradeType": "EXACT_INPUT",
            "protocols": ["V3"]
        }
        
        headers = {
            "Content-Type": "application/json",
            "Origin": "https://pancakeswap.finance"
        }
        
        async with session.post(url, json=payload, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                quote = data.get("quote", {})
                amount_out_str = quote.get("quoteGasAdjusted") or quote.get("quote") or "0"
                
                # Parse amount (may be decimal string)
                if '.' in str(amount_out_str):
                    # Decimal amount - need to convert to wei
                    decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
                    amount_out = int(float(amount_out_str) * (10 ** decimals_out))
                else:
                    amount_out = int(amount_out_str)
                
                if amount_out > 0:
                    amount_in = int(amount)
                    decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
                    
                    price = (amount_out / (10 ** decimals_out)) / (amount_in / (10 ** 18))
                    
                    return {
                        "dex": "pancakeswap",
                        "output": amount_out,
                        "price": price,
                        "fee_tier": 2500,
                        "fee_decimal": 0.0025,
                        "price_impact": None,
                        "liquidity": None,
                    }
    except Exception as e:
        logger.debug(f"[BASE] PancakeSwap smart router error: {e}")
    
    return None


async def _get_pancake_via_0x(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str
) -> Optional[Dict[str, Any]]:
    """Get PancakeSwap price via 0x API."""
    try:
        url = "https://base.api.0x.org/swap/v1/quote"
        params = {
            "sellToken": token_in,
            "buyToken": token_out,
            "sellAmount": amount,
            "excludedSources": "Uniswap_V3,Aerodrome,KyberSwap"  # Only PancakeSwap-like sources
        }
        
        headers = {
            "0x-api-key": "",  # Public endpoint
            "Accept": "application/json"
        }
        
        async with session.get(url, params=params, headers=headers, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                buy_amount = int(data.get("buyAmount", 0))
                
                if buy_amount > 0:
                    amount_in = int(amount)
                    decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
                    
                    price = (buy_amount / (10 ** decimals_out)) / (amount_in / (10 ** 18))
                    
                    return {
                        "dex": "pancakeswap",
                        "output": buy_amount,
                        "price": price,
                        "fee_tier": 2500,
                        "fee_decimal": 0.0025,
                        "price_impact": float(data.get("estimatedPriceImpact", 0)),
                        "liquidity": None,
                    }
    except Exception as e:
        logger.debug(f"[BASE] 0x API error: {e}")
    
    # Final fallback: DeFiLlama
    return await _get_price_via_defillama(session, token_in, "pancakeswap")


# =============================================================================
# KYBERSWAP PRICE FETCHER (from existing code)
# =============================================================================

async def get_kyberswap_price(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str,
    amount: str = DEFAULT_AMOUNT_18
) -> Optional[Dict[str, Any]]:
    """
    Fetch quote from KyberSwap on Base.
    
    API: https://aggregator-api.kyberswap.com/base/api/v1/routes
    
    Already implemented in price_fetchers.py, this is a wrapper
    that returns the structured format.
    """
    try:
        url = f"https://aggregator-api.kyberswap.com/base/api/v1/routes"
        
        params = {
            "tokenIn": token_in,
            "tokenOut": token_out,
            "amountIn": amount,
        }
        
        async with session.get(url, params=params, timeout=10) as resp:
            if resp.status == 200:
                data = await resp.json()
                
                route_summary = data.get("data", {}).get("routeSummary", {})
                amount_out = int(route_summary.get("amountOut", 0))
                
                # Gas and price info
                gas_usd = float(route_summary.get("gasUsd", 0))
                
                if amount_out > 0:
                    amount_in = int(amount)
                    decimals_out = 6 if token_out.lower() == USDC_BASE.lower() else 18
                    decimals_in = 18
                    
                    price = (amount_out / (10 ** decimals_out)) / (amount_in / (10 ** decimals_in))
                    
                    return {
                        "dex": "kyberswap",
                        "output": amount_out,
                        "price": price,
                        "fee_decimal": 0.001,  # 0.10%
                        "price_impact": None,
                        "liquidity": None,
                        "gas_usd": gas_usd,
                    }
            else:
                logger.debug(f"[BASE] KyberSwap API status: {resp.status}")
                
    except asyncio.TimeoutError:
        logger.debug("[BASE] KyberSwap timeout")
    except Exception as e:
        logger.debug(f"[BASE] KyberSwap error: {e}")
    
    return None


# =============================================================================
# BATCH PRICE FETCHER FOR ALL BASE DEX
# =============================================================================

async def get_all_base_dex_prices(
    session: aiohttp.ClientSession,
    token_in: str,
    token_out: str = USDC_BASE,
    amount: str = DEFAULT_AMOUNT_18
) -> Dict[str, Optional[Dict[str, Any]]]:
    """
    Fetch prices from all 4 Base DEX in parallel.
    
    Returns dict with structured quote data for each DEX.
    """
    # Fetch all DEX in parallel
    results = await asyncio.gather(
        get_uniswap_price(session, token_in, token_out, amount),
        get_aerodrome_price(session, token_in, token_out, amount),
        get_pancakeswap_price(session, token_in, token_out, amount),
        get_kyberswap_price(session, token_in, token_out, amount),
        return_exceptions=True
    )
    
    dex_names = ["uniswap", "aerodrome", "pancakeswap", "kyberswap"]
    
    prices = {}
    for i, result in enumerate(results):
        dex_name = dex_names[i]
        if isinstance(result, dict):
            prices[dex_name] = result
        elif isinstance(result, Exception):
            logger.debug(f"[BASE] {dex_name} exception: {result}")
            prices[dex_name] = None
        else:
            prices[dex_name] = None
    
    return prices


# =============================================================================
# BASE ARBITRAGE EVALUATION
# =============================================================================

async def evaluate_base_arbitrage(
    session: aiohttp.ClientSession,
    token: str,
    base_token: str = USDC_BASE,
    amount: str = DEFAULT_AMOUNT_18,
    min_spread: float = 0.003
) -> Optional[Dict[str, Any]]:
    """
    Evaluate arbitrage opportunity on Base chain.
    
    This function:
    1. Fetches prices from all 4 Base DEX
    2. Compares prices ONLY between Base DEX
    3. Calculates costs (fees, slippage, MEV)
    4. Returns structured opportunity if spread_net > min_spread
    
    Args:
        session: aiohttp session
        token: Token address to evaluate
        base_token: Quote token (USDC)
        amount: Amount for quote
        min_spread: Minimum net spread required
    
    Returns:
        Opportunity dict or None
    """
    # Fetch all prices
    all_quotes = await get_all_base_dex_prices(session, token, base_token, amount)
    
    # Filter valid quotes
    valid_quotes = {
        dex: quote for dex, quote in all_quotes.items()
        if quote is not None and quote.get("price", 0) > 0
    }
    
    if len(valid_quotes) < 2:
        logger.debug(f"[BASE] {token[:8]}: Not enough DEX ({len(valid_quotes)}/2)")
        return None
    
    # Find best buy (lowest price) and sell (highest price)
    prices = {dex: q["price"] for dex, q in valid_quotes.items()}
    
    buy_dex = min(prices, key=prices.get)
    sell_dex = max(prices, key=prices.get)
    
    buy_price = prices[buy_dex]
    sell_price = prices[sell_dex]
    
    if buy_price <= 0:
        return None
    
    # Calculate spread_brut
    spread_brut = (sell_price - buy_price) / buy_price
    
    # Get fee data from quotes
    buy_quote = valid_quotes[buy_dex]
    sell_quote = valid_quotes[sell_dex]
    
    buy_fee = buy_quote.get("fee_decimal", BASE_DEX_FEES.get(buy_dex, 0.003))
    sell_fee = sell_quote.get("fee_decimal", BASE_DEX_FEES.get(sell_dex, 0.003))
    
    # Estimate liquidity (use lowest available)
    liquidity = None
    for q in valid_quotes.values():
        liq = q.get("liquidity")
        if liq is not None:
            if liquidity is None or liq < liquidity:
                liquidity = liq
    
    # Default liquidity if unknown
    if liquidity is None:
        liquidity = 50_000  # Assume $50k
    
    # Calculate costs
    dex_fees = buy_fee + sell_fee
    network_fee = 0.001  # 0.10% Base network
    slippage = estimate_base_slippage(liquidity) * 2  # Buy + Sell
    mev_penalty = calculate_base_mev_penalty(liquidity)
    
    # Price impact from quotes
    buy_impact = buy_quote.get("price_impact", 0) or 0
    sell_impact = sell_quote.get("price_impact", 0) or 0
    total_price_impact = abs(buy_impact) + abs(sell_impact)
    
    # Total costs
    total_costs = dex_fees + network_fee + slippage + mev_penalty + total_price_impact
    
    # Net spread
    spread_net = spread_brut - total_costs
    
    # Check minimum spread
    if spread_net < min_spread:
        logger.debug(
            f"[BASE] {token[:8]}: Net spread {spread_net*100:.3f}% < min {min_spread*100:.2f}%"
        )
        return None
    
    # Calculate confidence score (simplified for Base)
    dex_count = len(valid_quotes)
    confidence = min(100, dex_count * 25)  # 4 DEX = 100%
    
    if liquidity >= 100_000:
        confidence = min(100, confidence + 10)
    elif liquidity < 30_000:
        confidence = max(0, confidence - 20)
    
    # Profit estimate
    swap_size = 1000  # $1000
    profit_estimate = swap_size * spread_net
    
    # Build result
    return {
        "chain": "base",
        "token": token,
        "base_token": base_token,
        "buy_dex": buy_dex,
        "sell_dex": sell_dex,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "prices": prices,
        "dex_count": dex_count,
        "spread_brut": spread_brut,
        "spread_net": spread_net,
        "fees": {
            "dex_buy": buy_fee,
            "dex_sell": sell_fee,
            "total_dex": dex_fees,
            "network": network_fee,
            "slippage": slippage,
            "mev": mev_penalty,
            "price_impact": total_price_impact,
            "total": total_costs,
        },
        "liquidity": liquidity,
        "confidence": confidence,
        "profit_estimate_usd": profit_estimate,
        "buy_url": get_base_swap_url(buy_dex, base_token, token),
        "sell_url": get_base_swap_url(sell_dex, token, base_token),
    }


# =============================================================================
# BASE DEX SWAP URLS
# =============================================================================

BASE_DEX_URLS = {
    "uniswap": "https://app.uniswap.org/#/swap?inputCurrency={token_in}&outputCurrency={token_out}&chain=base",
    "aerodrome": "https://aerodrome.finance/swap?from={token_in}&to={token_out}",
    "pancakeswap": "https://pancakeswap.finance/swap?chain=base&inputCurrency={token_in}&outputCurrency={token_out}",
    "kyberswap": "https://kyberswap.com/swap/base/{token_in}-to-{token_out}",
}


def get_base_swap_url(dex: str, token_in: str, token_out: str) -> str:
    """Generate swap URL for a Base DEX."""
    template = BASE_DEX_URLS.get(dex.lower())
    if template:
        return template.format(token_in=token_in, token_out=token_out)
    return f"https://basescan.org/token/{token_out}"


def get_base_arbitrage_links(opportunity: Dict) -> Dict[str, str]:
    """
    Generate buy and sell links for a Base arbitrage opportunity.
    
    Returns:
        {"buy_link": "...", "sell_link": "..."}
    """
    return {
        "buy_link": opportunity.get("buy_url", ""),
        "sell_link": opportunity.get("sell_url", ""),
    }

