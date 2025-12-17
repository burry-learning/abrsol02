# arbitrage.py
"""
Advanced Arbitrage Detection Module - v2.1

This module implements a smart arbitrage detection system with:
- Adaptive slippage based on token type and liquidity
- Realistic DEX-specific fees
- Dynamic price impact based on liquidity depth
- Multi-factor confidence scoring
- MEV protection through risk assessment

Supported DEX (Solana):
- Jupiter, Raydium, Orca, Meteora, Phoenix, Lifinity

Supported DEX (Base):
- Uniswap V3, Aerodrome Finance, PancakeSwap V3, KyberSwap
"""
import asyncio
from typing import Dict, Optional, List, Any
from config import MIN_SPREAD_AFTER_FEES
from utils import logger
from fees import estimate_network_fee
import json

# Import pool-based fetchers
from pool_prices import get_pool_prices_for_token, filter_pools_by_liquidity, sort_pools_by_buy_price, sort_pools_by_sell_price

# Import Base DEX module
try:
    from base_dex_fetchers import (
        get_all_base_dex_prices,
        evaluate_base_arbitrage,
        BASE_DEX_FEES,
        estimate_base_slippage,
        calculate_base_mev_penalty,
        get_base_swap_url,
        WETH_BASE,
        USDC_BASE,
    )
    BASE_MODULE_AVAILABLE = True
except ImportError:
    BASE_MODULE_AVAILABLE = False
    logger.warning("[ARB] Base module not available - Base chain disabled")


# =============================================================================
# DEX FEE TABLE (Realistic values)
# =============================================================================

# Solana DEX Fees
SOLANA_DEX_FEES = {
    "jupiter": 0.0010,    # 0.10% - Aggregator fee
    "raydium": 0.0025,    # 0.25% - Standard AMM
    "orca": 0.0022,       # 0.22% - Whirlpool average
    "meteora": 0.0010,    # 0.10% - DLMM (dynamic, can be 0.05-0.2%)
    "phoenix": 0.0004,    # 0.04% - Order book (very low)
    "lifinity": 0.0020,   # 0.20% - PMM
    "pumpfun": 0.0100,    # 1.00% - High fee DEX
    "openbook": 0.0004,   # 0.04% - Order book
}

# Base DEX Fees (detailed with endpoint-specific values)
BASE_DEX_FEES_TABLE = {
    "uniswap": 0.0030,      # 0.30% default (actual tier from endpoint preferred)
    "aerodrome": 0.0004,    # 0.04% ve(3,3) model
    "pancakeswap": 0.0025,  # 0.25% default (actual tier from endpoint preferred)
    "kyberswap": 0.0010,    # 0.10%
}

# Combined DEX_FEES for backward compatibility
DEX_FEES = {**SOLANA_DEX_FEES, **BASE_DEX_FEES_TABLE}

# Network fees are now dynamically estimated in fees.py


# =============================================================================
# TOKEN CATEGORIES (for slippage estimation)
# =============================================================================

# Major tokens with high liquidity - lowest slippage
MAJOR_TOKENS = {
    "So11111111111111111111111111111111111111112",   # SOL
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",  # USDC
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",  # USDT
    "mSoLzYCxHdYgdzU16g5QSh3i5K3z3KZK7ytfqcJm7So",  # mSOL
    "7dHbWXmci3dT8UFYWYZweBLXgycu7Y3iL6trKn1Y7ARj",  # stSOL
}

# Medium liquidity tokens
MEDIUM_TOKENS = {
    "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",  # BONK
    "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm",  # WIF
    "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3",  # PYTH
    "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN",   # JUP
    "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R",  # RAY
}


# =============================================================================
# SMART SLIPPAGE ESTIMATION
# =============================================================================

def estimate_slippage(
    token_mint: str,
    liquidity_usd: float,
    swap_size_usd: float = 1000,
    fee_bps: Optional[int] = None,
    price_coherence: float = 1.0,
    pool_count: int = 1
) -> float:
    """
    Estimate slippage based on token category, liquidity, swap size, and pool fee tier.
    
    Returns slippage as decimal (e.g., 0.001 = 0.1%)
    
    Factors:
    - Token category (major/medium/microcap)
    - Liquidity depth
    - Swap size relative to liquidity
    - Pool fee tier (higher fees often indicate less liquid pairs)
    
    Categories:
    - Major tokens (SOL, USDC, USDT): 0.05%
    - Medium tokens (BONK, WIF, JUP): 0.15-0.25%
    - Microcaps: 0.4-0.6%
    """
    # Base slippage by token category
    if token_mint in MAJOR_TOKENS:
        base_slippage = 0.0005  # 0.05%
    elif token_mint in MEDIUM_TOKENS:
        base_slippage = 0.0020  # 0.20%
    else:
        # Unknown token = microcap
        base_slippage = 0.0040  # 0.40%

    # Price coherence factor: lower coherence = higher slippage
    coherence_multiplier = max(0.5, 2.0 - price_coherence)  # 0.5x to 2.0x
    base_slippage *= coherence_multiplier

    # Pool count factor: fewer pools = higher slippage risk
    pool_multiplier = max(1.0, 2.0 - (pool_count * 0.2))  # More pools = lower multiplier
    base_slippage *= pool_multiplier
    
    # Liquidity adjustment multiplier
    if liquidity_usd >= 1_000_000:
        liq_multiplier = 0.5   # Very liquid, reduce slippage
    elif liquidity_usd >= 500_000:
        liq_multiplier = 0.75
    elif liquidity_usd >= 100_000:
        liq_multiplier = 1.0   # Normal
    elif liquidity_usd >= 50_000:
        liq_multiplier = 1.25
    elif liquidity_usd >= 10_000:
        liq_multiplier = 1.5
    else:
        liq_multiplier = 2.0   # Very illiquid, increase slippage
    
    # Swap size impact: larger swaps relative to liquidity = more slippage
    # Formula: impact = (swap_size / liquidity) ^ 0.7 (sub-linear growth)
    if liquidity_usd > 0:
        size_ratio = swap_size_usd / liquidity_usd
        # Cap size_ratio at 0.1 (10% of pool) for safety
        size_ratio = min(size_ratio, 0.1)
        size_multiplier = 1 + (size_ratio ** 0.7) * 2.0  # Max 2x for 10% of pool
    else:
        size_multiplier = 2.0  # Very conservative if no liquidity data
    
    # Fee tier adjustment: higher fees often indicate lower liquidity
    fee_multiplier = 1.0
    if fee_bps:
        if fee_bps >= 300:  # 0.3%+ fees usually mean less liquid
            fee_multiplier = 1.2
        elif fee_bps >= 100:  # 0.1%+ standard
            fee_multiplier = 1.0
        else:  # < 0.1% very low fees (often high volume pairs)
            fee_multiplier = 0.9
    
    slippage = base_slippage * liq_multiplier * size_multiplier * fee_multiplier
    
    # Cap slippage at reasonable bounds
    return min(max(slippage, 0.0005), 0.015)  # 0.05% to 1.5%


# =============================================================================
# SMART PRICE IMPACT ESTIMATION
# =============================================================================

def estimate_price_impact(liquidity_usd: float, swap_size_usd: float = 1000) -> float:
    """
    Estimate price impact based on liquidity depth.
    
    Returns price impact as decimal (e.g., 0.001 = 0.1%)
    
    Liquidity tiers:
    - > $1M:      0.05%
    - $200k-1M:   0.10%
    - $20k-200k:  0.20%
    - < $20k:     0.50%
    """
    if liquidity_usd >= 1_000_000:
        base_impact = 0.0005  # 0.05%
    elif liquidity_usd >= 200_000:
        base_impact = 0.0010  # 0.10%
    elif liquidity_usd >= 20_000:
        base_impact = 0.0020  # 0.20%
    else:
        base_impact = 0.0050  # 0.50%
    
    # Adjust for swap size (larger swaps = more impact)
    size_multiplier = (swap_size_usd / 1000) ** 0.5  # Square root scaling
    
    impact = base_impact * size_multiplier
    
    # Cap at reasonable bounds
    return min(max(impact, 0.0005), 0.02)  # 0.05% to 2%


# =============================================================================
# PRICE COHERENCE SCORING
# =============================================================================

def calculate_price_coherence(prices: Dict[str, float]) -> float:
    """
    Calculate how coherent prices are across DEX.
    
    High coherence = prices are similar = reliable
    Low coherence = prices vary wildly = suspicious
    
    Returns score from 0 to 1 (1 = perfect coherence)
    """
    if len(prices) < 2:
        return 0.0
    
    price_values = list(prices.values())
    avg_price = sum(price_values) / len(price_values)
    
    if avg_price == 0:
        return 0.0
    
    # Calculate coefficient of variation (CV)
    variance = sum((p - avg_price) ** 2 for p in price_values) / len(price_values)
    std_dev = variance ** 0.5
    cv = std_dev / avg_price
    
    # Convert CV to coherence score (lower CV = higher coherence)
    # CV of 0 = perfect coherence (score 1.0)
    # CV of 0.1 (10% variation) = low coherence (score ~0.3)
    coherence = max(0, 1 - (cv * 10))
    
    return min(coherence, 1.0)


# =============================================================================
# VOLATILITY RISK ASSESSMENT
# =============================================================================

def assess_volatility_risk(spread_brut: float, price_coherence: float) -> float:
    """
    Assess volatility risk based on spread and price coherence.
    
    High spread + low coherence = high volatility risk
    
    Returns risk score from 0 to 1 (0 = safe, 1 = very risky)
    """
    # High spread indicates potential volatility
    spread_risk = min(spread_brut * 10, 1.0)  # 10% spread = max risk
    
    # Low coherence indicates unstable prices
    coherence_risk = 1 - price_coherence
    
    # Combined risk
    risk = (spread_risk * 0.4) + (coherence_risk * 0.6)
    
    return min(max(risk, 0), 1.0)


# =============================================================================
# ADVANCED CONFIDENCE SCORE
# =============================================================================

def calculate_confidence_score(
    prices: Dict[str, float],
    liquidity_usd: float,
    volume_24h: float,
    spread_brut: float
) -> int:
    """
    Calculate a comprehensive confidence score (0-100).
    
    Factors:
    - Price coherence (30%): How similar are prices across DEX?
    - Liquidity depth (30%): Is there enough liquidity?
    - Volatility check (20%): Is the token stable?
    - DEX availability (10%): How many DEX have prices?
    - Volume 24h (10%): Is there trading activity?
    """
    dex_count = len(prices)
    
    # 1. Price coherence (30 points)
    price_coherence = calculate_price_coherence(prices)
    coherence_score = price_coherence * 30
    
    # 2. Liquidity depth (30 points)
    if liquidity_usd >= 500_000:
        liq_score = 30
    elif liquidity_usd >= 100_000:
        liq_score = 25
    elif liquidity_usd >= 50_000:
        liq_score = 20
    elif liquidity_usd >= 10_000:
        liq_score = 10
    else:
        liq_score = 5
    
    # 3. Volatility check (20 points)
    volatility_risk = assess_volatility_risk(spread_brut, price_coherence)
    volatility_score = (1 - volatility_risk) * 20
    
    # 4. DEX availability (10 points)
    if dex_count >= 4:
        dex_score = 10
    elif dex_count >= 3:
        dex_score = 7
    elif dex_count >= 2:
        dex_score = 4
    else:
        dex_score = 0
    
    # 5. Volume 24h (10 points)
    if volume_24h >= 1_000_000:
        volume_score = 10
    elif volume_24h >= 100_000:
        volume_score = 7
    elif volume_24h >= 10_000:
        volume_score = 4
    else:
        volume_score = 2
    
    # Total score
    total = coherence_score + liq_score + volatility_score + dex_score + volume_score
    
    return int(min(max(total, 0), 100))


# =============================================================================
# MEV RISK ASSESSMENT
# =============================================================================

def assess_mev_risk(
    token_mint: str,
    liquidity_usd: float,
    spread_brut: float
) -> Dict[str, any]:
    """
    Assess MEV (front-running) risk.
    
    Returns dict with:
    - risk_level: "low", "medium", "high"
    - slippage_buffer: additional slippage to add
    - should_reject: whether to reject this opportunity
    """
    risk_level = "low"
    slippage_buffer = 0.0
    should_reject = False
    reason = None
    
    # High spread + low liquidity = MEV target
    if spread_brut > 0.05 and liquidity_usd < 50_000:
        risk_level = "high"
        slippage_buffer = 0.005  # Add 0.5% buffer
        should_reject = True
        reason = "High spread with low liquidity - likely MEV bait"
    
    # Very low liquidity = easy to manipulate
    elif liquidity_usd < 10_000:
        risk_level = "high"
        slippage_buffer = 0.005
        should_reject = True
        reason = "Liquidity too low - high manipulation risk"
    
    # Medium risk scenarios
    elif liquidity_usd < 50_000 or spread_brut > 0.03:
        risk_level = "medium"
        slippage_buffer = 0.002  # Add 0.2% buffer
    
    # Major tokens are safer
    if token_mint in MAJOR_TOKENS:
        risk_level = "low"
        slippage_buffer = 0.0
        should_reject = False
        reason = None
    
    return {
        "risk_level": risk_level,
        "slippage_buffer": slippage_buffer,
        "should_reject": should_reject,
        "reason": reason
    }


# =============================================================================
# MAIN ARBITRAGE DETECTION FUNCTION
# =============================================================================

async def compute_spread_and_metrics(
    session, 
    token_mint: str, 
    base_mint: str = "So11111111111111111111111111111111111111112",
    liquidity_usd: float = 100_000,
    volume_24h: float = 50_000,
    swap_size_usd: float = 1000
) -> Optional[Dict]:
    """
    Advanced arbitrage opportunity detection using REAL POOLS (pool-to-pool).
    
    Steps:
    1. Fetch ALL pools containing this token from all DEX
    2. Filter pools by liquidity
    3. Find best buy pool (lowest buy_price) and best sell pool (highest sell_price)
    4. Calculate spread_brut (NO early filtering)
    5. Compute smart costs using ACTUAL pool fees
    6. Compute spread_net
    7. Filter based on MIN_SPREAD_AFTER_FEES
    8. Build confidence score
    9. Return structured opportunity dict with pool URLs
    
    Args:
        session: aiohttp session
        token_mint: Token address
        base_mint: Base token (SOL/USDC)
        liquidity_usd: Estimated liquidity (for smart calculations)
        volume_24h: 24h volume (for confidence score)
        swap_size_usd: Intended swap size (for price impact)
    
    Returns:
        Opportunity dict or None (with buy_pool_url, sell_pool_url, etc.)
    """
    
    # =========================================================================
    # STEP 1: Fetch ALL pools for this token
    # =========================================================================
    
    logger.debug(f"[ARB-POOL] Fetching pools for {token_mint[:8]}...")
    
    pools = await get_pool_prices_for_token(session, token_mint, base_mint)
    
    # Filter by minimum liquidity
    pools = filter_pools_by_liquidity(pools, min_liquidity_usd=10000)
    
    if len(pools) < 2:
        logger.debug(f"[ARB-POOL] {token_mint[:8]}: Not enough pools ({len(pools)}/2)")
        return None
    
    logger.info(f"[ARB-POOL] Token {token_mint[:8]}: {len(pools)} pools found")
    
    # Guardrail: cohérence minimale des prix disponibles
    if len(set(p.get("dex") for p in pools)) < 2:
        logger.debug(f"[ARB-POOL] {token_mint[:8]}: Not enough distinct DEX/pools")
        return None
    
    # =========================================================================
    # STEP 2: Find best buy and sell pools
    # =========================================================================
    
    # Sort by buy_price (lowest = best to buy from)
    sorted_by_buy = sort_pools_by_buy_price(pools)
    buy_pool = sorted_by_buy[0]  # Best buy pool (lowest price)
    
    # Sort by sell_price (highest = best to sell to)
    sorted_by_sell = sort_pools_by_sell_price(pools)
    sell_pool = sorted_by_sell[0]  # Best sell pool (highest price)
    
    # Ensure we're not using the same pool for buy and sell
    if buy_pool.get("pool_id") == sell_pool.get("pool_id"):
        if len(pools) < 3:
            logger.debug(f"[ARB-POOL] {token_mint[:8]}: Only one pool available")
            return None
        # Use second best sell pool
        sell_pool = sorted_by_sell[1]
    
    buy_price = buy_pool.get("buy_price")
    sell_price = sell_pool.get("sell_price")
    buy_dex = buy_pool.get("dex")
    sell_dex = sell_pool.get("dex")
    buy_pool_id = buy_pool.get("pool_id")
    sell_pool_id = sell_pool.get("pool_id")
    buy_pool_url = buy_pool.get("url")
    sell_pool_url = sell_pool.get("url")
    
    # =========================================================================
    # STEP 3: Calculate spread_brut
    # =========================================================================
    
    if buy_price <= 0 or sell_price <= 0:
        return None
    
    spread_brut = (sell_price - buy_price) / buy_price
    
    # Calculate price coherence from all pools
    all_prices = {p.get("dex"): p.get("buy_price") for p in pools if p.get("buy_price")}
    price_coherence = calculate_price_coherence(all_prices)
    
    # Guardrail: éviter les spreads irréalistes avec faible cohérence
    if len(pools) < 3 and spread_brut > 0.10 and price_coherence < 0.8:
        logger.warning(
            f"[ARB-POOL] Skip: spread {spread_brut*100:.2f}% avec {len(pools)} pools incohérents (coherence: {price_coherence:.2f})"
        )
        return None
    
    # Guardrail: bloquer spreads > 20% même avec cohérence (probablement une erreur de prix)
    if spread_brut > 0.20:
        logger.warning(
            f"[ARB-POOL] Skip: spread {spread_brut*100:.2f}% trop élevé (probable erreur de prix)"
        )
        return None
    
    # Guardrail: vérifier cohérence prix buy/sell dans chaque pool
    # Si buy_price > sell_price pour la même pool, c'est suspect
    buy_price_check = buy_pool.get("buy_price")
    sell_price_check = buy_pool.get("sell_price")
    if buy_price_check and sell_price_check and buy_price_check > sell_price_check:
        logger.warning(
            f"[ARB-POOL] Skip: prix incohérents dans buy_pool (buy: {buy_price_check:.6f} > sell: {sell_price_check:.6f})"
        )
        return None
    
    buy_price_check2 = sell_pool.get("buy_price")
    sell_price_check2 = sell_pool.get("sell_price")
    if buy_price_check2 and sell_price_check2 and buy_price_check2 > sell_price_check2:
        logger.warning(
            f"[ARB-POOL] Skip: prix incohérents dans sell_pool (buy: {buy_price_check2:.6f} > sell: {sell_price_check2:.6f})"
        )
        return None
    
    # =========================================================================
    # STEP 4: Compute smart costs using ACTUAL pool fees
    # =========================================================================
    
    # 4a. Use ACTUAL pool fees (not DEX defaults)
    buy_pool_fee_pct = buy_pool.get("fee_pct", 0.003)
    sell_pool_fee_pct = sell_pool.get("fee_pct", 0.003)
    total_dex_fees = buy_pool_fee_pct + sell_pool_fee_pct
    
    # 4b. Network fee (dynamic estimation)
    network_fee = estimate_network_fee("solana", swap_size_usd)
    
    # 4c. Smart slippage (adaptive) - use actual pool liquidity and swap size
    buy_pool_liq = buy_pool.get("liquidity_usd", liquidity_usd)
    sell_pool_liq = sell_pool.get("liquidity_usd", liquidity_usd)
    avg_pool_liq = (buy_pool_liq + sell_pool_liq) / 2

    # Guardrail: éviter les pools trop illiquides
    if avg_pool_liq < 10_000:
        logger.debug(f"[ARB-POOL] {token_mint[:8]}: liquidity too low ({avg_pool_liq:.0f} USD)")
        return None
    
    # Guardrail: vérifier que les pools ont assez de liquidité partagée
    min_pool_liq = min(buy_pool_liq, sell_pool_liq)
    if min_pool_liq < 5_000:
        logger.debug(f"[ARB-POOL] {token_mint[:8]}: one pool too illiquid (min: {min_pool_liq:.0f} USD)")
        return None

    # Slippage réaliste basé sur swap_size, profondeur de pool, cohérence et nombre de pools
    buy_pool_fee_bps = buy_pool.get("fee_bps", 25)
    sell_pool_fee_bps = sell_pool.get("fee_bps", 25)

    # Slippage pour chaque pool individuellement avec facteurs avancés
    buy_slippage = estimate_slippage(
        token_mint, buy_pool_liq, swap_size_usd, buy_pool_fee_bps,
        price_coherence, len(pools)
    )
    sell_slippage = estimate_slippage(
        token_mint, sell_pool_liq, swap_size_usd, sell_pool_fee_bps,
        price_coherence, len(pools)
    )
    base_slippage = (buy_slippage + sell_slippage) / 2
    
    # 4d. MEV risk assessment
    mev_assessment = assess_mev_risk(token_mint, avg_pool_liq, spread_brut)
    slippage_buffer = mev_assessment["slippage_buffer"]
    
    # Total slippage (buy + sell + MEV buffer)
    total_slippage = buy_slippage + sell_slippage + slippage_buffer
    
    # 4e. Smart price impact (use actual pool liquidity)
    price_impact = estimate_price_impact(avg_pool_liq, swap_size_usd)
    
    # 4f. Total costs
    total_costs = total_dex_fees + network_fee + total_slippage + price_impact
    
    # =========================================================================
    # STEP 5: Compute spread_net
    # =========================================================================
    
    spread_net = spread_brut - total_costs
    
    # =========================================================================
    # STEP 6: Filter based on spread_net
    # =========================================================================
    
    # Check MEV rejection first
    if mev_assessment["should_reject"]:
        logger.warning(
            f"[ARB-POOL] {token_mint[:8]}: REJECTED - {mev_assessment['reason']}"
        )
        return None
    
    # Check minimum spread
    if spread_net < MIN_SPREAD_AFTER_FEES:
        logger.debug(
            f"[ARB-POOL] {token_mint[:8]}: Spread net {spread_net*100:.3f}% < "
            f"min {MIN_SPREAD_AFTER_FEES*100:.2f}% | "
            f"Brut: {spread_brut*100:.2f}% | Costs: {total_costs*100:.2f}%"
        )
        return None
    
    # =========================================================================
    # STEP 7: Build confidence score
    # =========================================================================
    
    # Build prices dict from pools for coherence calculation
    pool_prices_dict = {p.get("dex"): p.get("buy_price") for p in pools if p.get("buy_price")}
    
    confidence_score = calculate_confidence_score(
        prices=pool_prices_dict,
        liquidity_usd=avg_pool_liq,
        volume_24h=volume_24h,
        spread_brut=spread_brut
    )
    
    # Guardrail 3: cohérence minimale avant envoi
    if price_coherence < 0.5:
        logger.warning(
            f"[ARB-POOL] Skip: cohérence trop faible ({price_coherence:.2f})"
        )
        return None
    
    # =========================================================================
    # STEP 8: Build result dict with POOL URLs
    # =========================================================================
    
    # Profit estimate
    profit_1000 = spread_net * swap_size_usd
    
    result = {
        # Token info
        "token": token_mint,
        "base": base_mint,
        "timestamp": asyncio.get_event_loop().time(),
        
        # Pool info (NEW - pool-to-pool)
        "buy_dex": buy_dex,
        "sell_dex": sell_dex,
        "buy_pool_id": buy_pool_id,
        "sell_pool_id": sell_pool_id,
        "buy_pool_url": buy_pool_url,
        "sell_pool_url": sell_pool_url,
        "buy_price": buy_price,
        "sell_price": sell_price,
        "pool_count": len(pools),
        
        # Backward compatibility
        "prices": pool_prices_dict,
        "dex_count": len(set(p.get("dex") for p in pools)),
        
        # Spreads
        "spread_brut": spread_brut,
        "spread_net": spread_net,
        
        # Cost breakdown (using ACTUAL pool fees)
        "costs": {
            "dex_fee_buy": buy_pool_fee_pct,
            "dex_fee_sell": sell_pool_fee_pct,
            "total_dex_fees": total_dex_fees,
            "network_fee": network_fee,
            "slippage_base": base_slippage,
            "slippage_buffer": slippage_buffer,
            "total_slippage": total_slippage,
        "price_impact": price_impact,
            "total_costs": total_costs,
        },
        
        # Deprecated (for backward compatibility)
        "total_fees_pct": total_dex_fees + network_fee,
        "slippage_est": total_slippage,
        "total_costs": total_costs,
        
        # Metrics (using actual pool liquidity)
        "liquidity_usd": avg_pool_liq,
        "volume_24h": volume_24h,
        "confidence_score": confidence_score,
        
        # MEV assessment
        "mev_risk": mev_assessment["risk_level"],
        
        # Profit estimate
        "profit_estimate_usd": profit_1000,
        
        # Flags
        "liquidity_check": avg_pool_liq >= 50_000,
        "volume_check": volume_24h >= 10_000,
        
        # Pool details for Telegram
        "details": {
            "buy_pool_fee_pct": buy_pool_fee_pct,
            "sell_pool_fee_pct": sell_pool_fee_pct,
            "buy_pool_fee_bps": buy_pool.get("fee_bps", 0),
            "sell_pool_fee_bps": sell_pool.get("fee_bps", 0),
            "buy_pool_liquidity": buy_pool_liq,
            "sell_pool_liquidity": sell_pool_liq,
            "network_fee": network_fee,
            "all_pools": pools,  # All pools for reference
        }
    }
    
    # =========================================================================
    # LOG OPPORTUNITY
    # =========================================================================
    
    logger.info("=" * 70)
    logger.info(f"[ARB-POOL] OPPORTUNITY DETECTED!")
    logger.info(f"Token: {token_mint[:8]}...")
    logger.info(f"Buy Pool: {buy_dex.upper()} @ ${buy_price:.6f} | Pool: {buy_pool_id[:8]}...")
    logger.info(f"Sell Pool: {sell_dex.upper()} @ ${sell_price:.6f} | Pool: {sell_pool_id[:8]}...")
    logger.info(f"Spread: Brut {spread_brut*100:.2f}% | Net {spread_net*100:.3f}%")
    logger.info(f"Costs breakdown:")
    logger.info(f"  Pool fees (buy): {buy_pool_fee_pct*100:.2f}% | (sell): {sell_pool_fee_pct*100:.2f}%")
    logger.info(f"  Slippage: {total_slippage*100:.3f}%")
    logger.info(f"  Price impact: {price_impact*100:.3f}%")
    logger.info(f"  Total: {total_costs*100:.2f}%")
    logger.info(f"Confidence: {confidence_score}/100 | MEV risk: {mev_assessment['risk_level']}")
    logger.info(f"Profit (${swap_size_usd}): ${profit_1000:.2f}")
    logger.info(f"Buy URL: {buy_pool_url}")
    logger.info(f"Sell URL: {sell_pool_url}")
    logger.info("=" * 70)
    
    # Log synthétique JSON pour observabilité
    log_entry = {
        "type": "opportunity_detected",
        "token": token_mint[:8] + "...",
        "chain": "solana",
        "buy_dex": buy_dex,
        "sell_dex": sell_dex,
        "buy_pool_id": buy_pool_id[:8] + "..." if buy_pool_id else None,
        "sell_pool_id": sell_pool_id[:8] + "..." if sell_pool_id else None,
        "spread_brut_pct": round(spread_brut * 100, 3),
        "spread_net_pct": round(spread_net * 100, 3),
        "buy_price": round(buy_price, 8),
        "sell_price": round(sell_price, 8),
        "costs_pct": round(total_costs * 100, 3),
        "confidence_score": confidence_score,
        "avg_liquidity_usd": round(avg_pool_liq, 0),
        "pool_count": len(pools),
        "mev_risk": mev_assessment["risk_level"],
        "price_coherence": round(price_coherence, 3),
        "timestamp": asyncio.get_event_loop().time()
    }
    logger.info(f"[JSON-LOG] {json.dumps(log_entry)}")
    
    return result


# =============================================================================
# BATCH SCANNER
# =============================================================================

async def find_best_arbitrage_opportunities(
    session,
    tokens: List[str],
    base_mint: str = "So11111111111111111111111111111111111111112",
    top_n: int = 5
) -> List[Dict]:
    """
    Scan multiple tokens for arbitrage opportunities.
    
    Args:
        session: aiohttp session
        tokens: List of token mints to scan
        base_mint: Base token (SOL/USDC)
        top_n: Max opportunities to return
    
    Returns:
        List of opportunities sorted by spread_net (descending)
    """
    logger.info(f"[ARB] Scanning {len(tokens)} tokens...")
    
    # Run all scans in parallel
    tasks = [
        compute_spread_and_metrics(session, token, base_mint)
        for token in tokens
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter valid results
    opportunities = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            opportunities.append(result)
        elif isinstance(result, Exception):
            logger.error(f"[ARB] Error for {tokens[i][:8]}: {result}")
    
    # Sort by spread_net descending
    opportunities.sort(key=lambda x: x.get("spread_net", 0), reverse=True)
    
    logger.info(f"[ARB] Found {len(opportunities)} opportunities")
    
    return opportunities[:top_n]


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def estimate_profit_usd(opportunity: Dict, investment_usd: float = 1000.0) -> float:
    """Estimate profit in USD for a given investment."""
    spread_net = opportunity.get("spread_net", 0)
    return investment_usd * spread_net


def get_opportunity_summary(opportunity: Dict) -> str:
    """Get a human-readable summary of an opportunity."""
    chain = opportunity.get("chain", "solana").upper()
    chain_emoji = "🔵" if chain == "BASE" else "🟣"
    
    return (
        f"{chain_emoji} {chain} | "
        f"Token: {opportunity['token'][:8]}... | "
        f"Buy: {opportunity['buy_dex'].upper()} @ ${opportunity['buy_price']:.6f} | "
        f"Sell: {opportunity['sell_dex'].upper()} @ ${opportunity['sell_price']:.6f} | "
        f"Net: {opportunity['spread_net']*100:.2f}% | "
        f"Conf: {opportunity['confidence_score']}/100"
    )


# =============================================================================
# POOL-TO-POOL PAIRWISE (used by main.py simple scanner)
# =============================================================================

def compute_pool_arbitrage(
    pool_a: Dict[str, Any],
    pool_b: Dict[str, Any],
    token: str
) -> Optional[Dict[str, Any]]:
    """
    Compare deux pools d'un même token et retourne une opportunité si spread net > 0.
    Hypothèses:
      - pool["buy_price"] et ["sell_price"] sont exprimés vs base (SOL/USDC).
      - pool["fee_pct"] est le fee effectif de la pool (en proportion).
    """
    try:
        buy_price_a = float(pool_a.get("buy_price") or 0)
        sell_price_a = float(pool_a.get("sell_price") or 0)
        buy_price_b = float(pool_b.get("buy_price") or 0)
        sell_price_b = float(pool_b.get("sell_price") or 0)

        if min(buy_price_a, sell_price_a, buy_price_b, sell_price_b) <= 0:
            return None

        # Scénario 1: buy on A, sell on B
        spread1_brut = (sell_price_b - buy_price_a) / buy_price_a
        fee1 = (pool_a.get("fee_pct", 0) or 0) + (pool_b.get("fee_pct", 0) or 0)
        spread1_net = spread1_brut - fee1

        # Scénario 2: buy on B, sell on A
        spread2_brut = (sell_price_a - buy_price_b) / buy_price_b
        fee2 = (pool_b.get("fee_pct", 0) or 0) + (pool_a.get("fee_pct", 0) or 0)
        spread2_net = spread2_brut - fee2

        # Choisir le meilleur sens
        if spread1_net <= 0 and spread2_net <= 0:
            return None

        if spread1_net >= spread2_net:
            buy_pool, sell_pool = pool_a, pool_b
            spread_brut, spread_net, total_fees = spread1_brut, spread1_net, fee1
            buy_price, sell_price = buy_price_a, sell_price_b
        else:
            buy_pool, sell_pool = pool_b, pool_a
            spread_brut, spread_net, total_fees = spread2_brut, spread2_net, fee2
            buy_price, sell_price = buy_price_b, sell_price_a

        return {
            "chain": buy_pool.get("chain") or sell_pool.get("chain") or "solana",
            "token": token,
            "buy_dex": buy_pool.get("dex"),
            "sell_dex": sell_pool.get("dex"),
            "buy_pool_id": buy_pool.get("pool_id"),
            "sell_pool_id": sell_pool.get("pool_id"),
            "buy_pool_url": buy_pool.get("url"),
            "sell_pool_url": sell_pool.get("url"),
            "buy_price": buy_price,
            "sell_price": sell_price,
            "spread_brut": spread_brut,
            "spread_net": spread_net,
            "total_fees_pct": total_fees,
            "details": {
                "buy_pool_fee_pct": buy_pool.get("fee_pct", 0),
                "sell_pool_fee_pct": sell_pool.get("fee_pct", 0),
                "buy_pool_liquidity": buy_pool.get("liquidity_usd", 0),
                "sell_pool_liquidity": sell_pool.get("liquidity_usd", 0),
                "pool_a": buy_pool,
                "pool_b": sell_pool,
            },
        }
    except Exception as e:
        pool_a_id = pool_a.get("pool_id", "unknown") if pool_a else "unknown"
        pool_b_id = pool_b.get("pool_id", "unknown") if pool_b else "unknown"
        dex_a = pool_a.get("dex", "unknown") if pool_a else "unknown"
        dex_b = pool_b.get("dex", "unknown") if pool_b else "unknown"
        logger.error(
            "[ARB] Error computing arbitrage token=%s pool_a=%s(%s) pool_b=%s(%s): %s",
            token[:8] if token else "unknown", pool_a_id[:8] if pool_a_id != "unknown" else "unknown", 
            dex_a, pool_b_id[:8] if pool_b_id != "unknown" else "unknown", dex_b, repr(e)
        )
        return None


# =============================================================================
# BASE CHAIN ARBITRAGE FUNCTIONS
# =============================================================================

async def compute_base_arbitrage(
    session,
    token: str,
    base_token: str = None,
    min_spread: float = None
) -> Optional[Dict]:
    """
    Evaluate arbitrage opportunity on BASE chain.
    
    Compares prices ONLY between Base DEX:
    - Uniswap V3
    - Aerodrome Finance
    - PancakeSwap V3
    - KyberSwap
    
    Args:
        session: aiohttp session
        token: Token address (ERC20)
        base_token: Quote token (default: USDC on Base)
        min_spread: Minimum net spread (default: MIN_SPREAD_AFTER_FEES)
    
    Returns:
        Structured opportunity dict or None
    """
    if not BASE_MODULE_AVAILABLE:
        logger.warning("[ARB] Base module not available")
        return None
    
    # Set defaults
    if base_token is None:
        base_token = USDC_BASE
    if min_spread is None:
        min_spread = MIN_SPREAD_AFTER_FEES
    
    # Use the Base module's evaluation function
    return await evaluate_base_arbitrage(
        session=session,
        token=token,
        base_token=base_token,
        min_spread=min_spread
    )


async def find_base_arbitrage_opportunities(
    session,
    tokens: List[str],
    base_token: str = None,
    top_n: int = 5
) -> List[Dict]:
    """
    Scan multiple BASE tokens for arbitrage opportunities.
    
    Args:
        session: aiohttp session
        tokens: List of Base token addresses to scan
        base_token: Quote token (default: USDC on Base)
        top_n: Max opportunities to return
    
    Returns:
        List of opportunities sorted by spread_net (descending)
    """
    if not BASE_MODULE_AVAILABLE:
        logger.warning("[ARB] Base module not available - returning empty")
        return []
    
    if base_token is None:
        base_token = USDC_BASE
    
    logger.info(f"[ARB-BASE] Scanning {len(tokens)} Base tokens...")
    
    # Run all scans in parallel
    tasks = [
        compute_base_arbitrage(session, token, base_token)
        for token in tokens
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter valid results
    opportunities = []
    for i, result in enumerate(results):
        if isinstance(result, dict):
            opportunities.append(result)
        elif isinstance(result, Exception):
            logger.error(f"[ARB-BASE] Error for {tokens[i][:8]}: {result}")
    
    # Sort by spread_net descending
    opportunities.sort(key=lambda x: x.get("spread_net", 0), reverse=True)
    
    logger.info(f"[ARB-BASE] Found {len(opportunities)} Base opportunities")
    
    return opportunities[:top_n]


# =============================================================================
# MULTI-CHAIN SCANNER
# =============================================================================

async def find_all_arbitrage_opportunities(
    session,
    solana_tokens: List[str] = None,
    base_tokens: List[str] = None,
    solana_base_mint: str = "So11111111111111111111111111111111111111112",
    base_quote_token: str = None,
    top_n: int = 10
) -> Dict[str, List[Dict]]:
    """
    Scan both Solana and Base chains for arbitrage opportunities.
    
    IMPORTANT: Solana opportunities are compared ONLY with other Solana DEX.
               Base opportunities are compared ONLY with other Base DEX.
               No cross-chain arbitrage.
    
    Args:
        session: aiohttp session
        solana_tokens: List of Solana token mints
        base_tokens: List of Base token addresses
        solana_base_mint: Base token for Solana (SOL)
        base_quote_token: Quote token for Base (USDC)
        top_n: Max opportunities per chain
    
    Returns:
        {
            "solana": [opportunities],
            "base": [opportunities],
            "total": int
        }
    """
    results = {
        "solana": [],
        "base": [],
        "total": 0
    }
    
    # Scan both chains in parallel
    tasks = []
    
    if solana_tokens:
        tasks.append(
            find_best_arbitrage_opportunities(
                session, solana_tokens, solana_base_mint, top_n
            )
        )
    else:
        tasks.append(asyncio.coroutine(lambda: [])())
    
    if base_tokens and BASE_MODULE_AVAILABLE:
        tasks.append(
            find_base_arbitrage_opportunities(
                session, base_tokens, base_quote_token, top_n
            )
        )
    else:
        tasks.append(asyncio.coroutine(lambda: [])())
    
    solana_results, base_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    if isinstance(solana_results, list):
        results["solana"] = solana_results
    elif isinstance(solana_results, Exception):
        logger.error(f"[ARB] Solana scan error: {solana_results}")
    
    if isinstance(base_results, list):
        results["base"] = base_results
    elif isinstance(base_results, Exception):
        logger.error(f"[ARB] Base scan error: {base_results}")
    
    results["total"] = len(results["solana"]) + len(results["base"])
    
    logger.info(
        f"[ARB] Multi-chain scan complete: "
        f"{len(results['solana'])} Solana + {len(results['base'])} Base"
    )
    
    return results


# =============================================================================
# BASE CHAIN HELPERS
# =============================================================================

def get_base_dex_fee(dex: str, endpoint_fee: float = None) -> float:
    """
    Get fee for a Base DEX.
    
    Uses endpoint fee if available, otherwise fallback to table.
    """
    if endpoint_fee is not None:
        return endpoint_fee
    return BASE_DEX_FEES_TABLE.get(dex.lower(), 0.003)


def format_base_opportunity(opportunity: Dict) -> str:
    """Format a Base opportunity for logging/display."""
    return (
        f"🔵 BASE | {opportunity['token'][:10]}...\n"
        f"   Buy: {opportunity['buy_dex'].upper()} @ ${opportunity['buy_price']:.6f}\n"
        f"   Sell: {opportunity['sell_dex'].upper()} @ ${opportunity['sell_price']:.6f}\n"
        f"   Spread: {opportunity['spread_net']*100:.2f}% net\n"
        f"   Profit ($1000): ${opportunity.get('profit_estimate_usd', 0):.2f}\n"
        f"   Confidence: {opportunity.get('confidence', 0)}/100"
    )
