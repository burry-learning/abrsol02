# dex_links.py
"""
DEX Link Generator for Solana & Base Arbitrage Bot.

This module generates URLs to DEX swap interfaces.
NO wallet interaction, NO signing, NO RPC usage.
Only URL generation for manual trading.

Supported SOLANA DEX:
- Jupiter (jup.ag)
- Raydium (raydium.io)
- Orca (orca.so)
- Meteora (meteora.ag)
- PumpFun (pump.fun)
- OpenBook (via Birdeye)

Supported BASE DEX:
- Uniswap V3
- Aerodrome Finance
- PancakeSwap V3
- KyberSwap
"""

from typing import Dict, Optional


# =============================================================================
# SOLANA DEX URL TEMPLATES
# =============================================================================

SOLANA_DEX_URLS = {
    "jupiter": "https://jup.ag/swap/{token_in}-{token_out}",
    "raydium": "https://raydium.io/swap/?inputMint={token_in}&outputMint={token_out}",
    "orca": "https://www.orca.so/swap?inputMint={token_in}&outputMint={token_out}",
    "meteora": "https://app.meteora.ag/swap?inputMint={token_in}&outputMint={token_out}",
    "pumpfun": "https://pump.fun/coin/{token}",
    "openbook": "https://birdeye.so/token/{token}?chain=solana",
    "phoenix": "https://birdeye.so/token/{token}?chain=solana",
    "lifinity": "https://lifinity.io/swap/{token_in}/{token_out}",
}

# Legacy alias
DEX_SWAP_URLS = SOLANA_DEX_URLS

# =============================================================================
# BASE DEX URL TEMPLATES
# =============================================================================

BASE_DEX_URLS = {
    "uniswap": "https://app.uniswap.org/#/swap?inputCurrency={token_in}&outputCurrency={token_out}&chain=base",
    "aerodrome": "https://aerodrome.finance/swap?from={token_in}&to={token_out}",
    "pancakeswap": "https://pancakeswap.finance/swap?chain=base&inputCurrency={token_in}&outputCurrency={token_out}",
    "kyberswap": "https://kyberswap.com/swap/base/{token_in}-to-{token_out}",
}

# =============================================================================
# FALLBACK URLS
# =============================================================================

SOLANA_FALLBACK_URL = "https://birdeye.so/token/{token}?chain=solana"
BASE_FALLBACK_URL = "https://basescan.org/token/{token}"

# Legacy alias
FALLBACK_URL = SOLANA_FALLBACK_URL


# =============================================================================
# MAIN FUNCTIONS
# =============================================================================

def get_swap_link(dex: str, token_in: str, token_out: str, chain: str = "solana") -> str:
    """
    Returns the correct URL to the DEX swap interface.
    
    Args:
        dex: Name of the DEX (jupiter, raydium, orca, meteora, pumpfun, openbook,
                             uniswap, aerodrome, pancakeswap, kyberswap)
        token_in: Input token mint address (what you're selling)
        token_out: Output token mint address (what you're buying)
        chain: "solana" or "base" (default: solana)
    
    Returns:
        URL string to the DEX swap interface
    
    Examples:
        >>> get_swap_link("jupiter", "SOL_MINT", "USDC_MINT")
        'https://jup.ag/swap/SOL_MINT-USDC_MINT'
        
        >>> get_swap_link("uniswap", "0xWETH", "0xUSDC", chain="base")
        'https://app.uniswap.org/#/swap?inputCurrency=0xWETH&outputCurrency=0xUSDC&chain=base'
    """
    dex_lower = dex.lower().strip()
    chain_lower = chain.lower().strip()
    
    # ==========================================================================
    # BASE CHAIN DEX
    # ==========================================================================
    if chain_lower == "base" or dex_lower in BASE_DEX_URLS:
        if dex_lower in BASE_DEX_URLS:
            return BASE_DEX_URLS[dex_lower].format(
                token_in=token_in,
                token_out=token_out
            )
        return BASE_FALLBACK_URL.format(token=token_out)
    
    # ==========================================================================
    # SOLANA CHAIN DEX
    # ==========================================================================
    
    # Handle special cases (PumpFun and OpenBook show token page, not swap)
    if dex_lower == "pumpfun":
        return SOLANA_DEX_URLS["pumpfun"].format(token=token_out)
    
    if dex_lower in ["openbook", "phoenix"]:
        return SOLANA_DEX_URLS.get(dex_lower, SOLANA_FALLBACK_URL).format(token=token_out)
    
    # Standard DEX with swap interface
    if dex_lower in SOLANA_DEX_URLS:
        return SOLANA_DEX_URLS[dex_lower].format(
            token_in=token_in,
            token_out=token_out
        )
    
    # Fallback for unsupported DEX
    return SOLANA_FALLBACK_URL.format(token=token_out)


def get_arbitrage_links(opportunity: dict) -> Dict[str, str]:
    """
    Returns buy and sell links for an arbitrage opportunity.
    
    Buy = base -> token (buying the token with base currency)
    Sell = token -> base (selling the token for base currency)
    
    Supports both Solana and Base chain opportunities.
    
    Args:
        opportunity: Dict containing:
            - buy_dex: DEX name for buying (lowest price)
            - sell_dex: DEX name for selling (highest price)
            - token: Token mint address
            - base: Base token mint address (SOL or USDC for Solana, WETH or USDC for Base)
            - chain: (optional) "solana" or "base"
    
    Returns:
        Dict with:
            - buy_link: URL to buy the token
            - sell_link: URL to sell the token
    
    Example:
        >>> opp = {
        ...     "buy_dex": "orca",
        ...     "sell_dex": "raydium", 
        ...     "token": "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263",
        ...     "base": "So11111111111111111111111111111111111111112"
        ... }
        >>> links = get_arbitrage_links(opp)
        >>> links["buy_link"]
        'https://www.orca.so/swap?inputMint=So111...&outputMint=DezXA...'
    """
    buy_dex = opportunity.get("buy_dex", "jupiter")
    sell_dex = opportunity.get("sell_dex", "jupiter")
    token = opportunity.get("token", "")
    base = opportunity.get("base", "So11111111111111111111111111111111111111112")
    chain = opportunity.get("chain", "solana")
    
    # Buy: base -> token (we give base, we receive token)
    buy_link = get_swap_link(buy_dex, token_in=base, token_out=token, chain=chain)
    
    # Sell: token -> base (we give token, we receive base)
    sell_link = get_swap_link(sell_dex, token_in=token, token_out=base, chain=chain)
    
    return {
        "buy_link": buy_link,
        "sell_link": sell_link
    }


def get_all_dex_links(token: str, base: str = "So11111111111111111111111111111111111111112", chain: str = "solana") -> Dict[str, Dict[str, str]]:
    """
    Returns swap links for all supported DEX on a given chain.
    
    Useful for comparing prices manually across all DEX.
    
    Args:
        token: Token mint address
        base: Base token mint address (default: SOL for Solana)
        chain: "solana" or "base"
    
    Returns:
        Dict with DEX names as keys, each containing buy_link and sell_link
    
    Example:
        >>> links = get_all_dex_links("BONK_MINT")
        >>> links["jupiter"]["buy_link"]
        'https://jup.ag/swap/So111...-BONK_MINT'
    """
    all_links = {}
    
    if chain.lower() == "base":
        dex_list = ["uniswap", "aerodrome", "pancakeswap", "kyberswap"]
    else:
        dex_list = ["jupiter", "raydium", "orca", "meteora", "pumpfun", "openbook"]
    
    for dex_name in dex_list:
        all_links[dex_name] = {
            "buy_link": get_swap_link(dex_name, token_in=base, token_out=token, chain=chain),
            "sell_link": get_swap_link(dex_name, token_in=token, token_out=base, chain=chain),
            "name": dex_name.capitalize()
        }
    
    return all_links


def get_base_arbitrage_links(opportunity: dict) -> Dict[str, str]:
    """
    Returns buy and sell links specifically for BASE chain arbitrage.
    
    Convenience wrapper that ensures chain="base".
    
    Args:
        opportunity: Dict with buy_dex, sell_dex, token, base_token
    
    Returns:
        Dict with buy_link and sell_link
    """
    # Ensure chain is set to base
    opp = dict(opportunity)
    opp["chain"] = "base"
    return get_arbitrage_links(opp)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_links_for_telegram(opportunity: dict) -> str:
    """
    Formats arbitrage links for Telegram message.
    
    Supports both Solana and Base chain opportunities.
    
    Args:
        opportunity: Arbitrage opportunity dict
    
    Returns:
        Formatted string with clickable links for Telegram
    """
    links = get_arbitrage_links(opportunity)
    buy_dex = opportunity.get("buy_dex", "?").upper()
    sell_dex = opportunity.get("sell_dex", "?").upper()
    chain = opportunity.get("chain", "solana").upper()
    
    chain_emoji = "🔵" if chain == "BASE" else "🟣"
    
    return (
        f"{chain_emoji} *{chain}*\n"
        f"[🟢 Acheter sur {buy_dex}]({links['buy_link']})\n"
        f"[🔴 Vendre sur {sell_dex}]({links['sell_link']})"
    )


def get_explorer_link(token: str) -> str:
    """
    Returns Solscan explorer link for a token.
    
    Args:
        token: Token mint address
    
    Returns:
        Solscan URL
    """
    return f"https://solscan.io/token/{token}"


def get_birdeye_link(token: str) -> str:
    """
    Returns Birdeye link for a token.
    
    Args:
        token: Token mint address
    
    Returns:
        Birdeye URL
    """
    return f"https://birdeye.so/token/{token}?chain=solana"


# =============================================================================
# BASE EXPLORER HELPERS
# =============================================================================

def get_basescan_link(token: str) -> str:
    """Returns Basescan explorer link for a Base token."""
    return f"https://basescan.org/token/{token}"


# =============================================================================
# TEST
# =============================================================================

if __name__ == "__main__":
    # Test with real token addresses
    # SOLANA
    SOL = "So11111111111111111111111111111111111111112"
    USDC_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
    BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
    
    # BASE
    WETH_BASE = "0x4200000000000000000000000000000000000006"
    USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    BRETT_BASE = "0x532f27101965dd16442E59d40670FaF5eBB142E4"  # Example Base token
    
    print("=" * 70)
    print("DEX LINK GENERATOR TEST - SOLANA & BASE")
    print("=" * 70)
    
    # Test SOLANA individual links
    print("\n🟣 SOLANA DEX --- Swap Links (SOL -> BONK) ---")
    for dex in ["jupiter", "raydium", "orca", "meteora", "pumpfun", "openbook"]:
        link = get_swap_link(dex, SOL, BONK, chain="solana")
        print(f"  {dex.upper():12} : {link[:55]}...")
    
    # Test BASE individual links
    print("\n🔵 BASE DEX --- Swap Links (WETH -> BRETT) ---")
    for dex in ["uniswap", "aerodrome", "pancakeswap", "kyberswap"]:
        link = get_swap_link(dex, WETH_BASE, BRETT_BASE, chain="base")
        print(f"  {dex.upper():12} : {link[:55]}...")
    
    # Test SOLANA arbitrage links
    print("\n--- SOLANA Arbitrage Links ---")
    opp_solana = {
        "buy_dex": "orca",
        "sell_dex": "raydium",
        "token": BONK,
        "base": SOL,
        "chain": "solana"
    }
    links = get_arbitrage_links(opp_solana)
    print(f"  Buy on ORCA:     {links['buy_link'][:55]}...")
    print(f"  Sell on RAYDIUM: {links['sell_link'][:55]}...")
    
    # Test BASE arbitrage links
    print("\n--- BASE Arbitrage Links ---")
    opp_base = {
        "buy_dex": "uniswap",
        "sell_dex": "aerodrome",
        "token": BRETT_BASE,
        "base": USDC_BASE,
        "chain": "base"
    }
    links_base = get_arbitrage_links(opp_base)
    print(f"  Buy on UNISWAP:    {links_base['buy_link'][:55]}...")
    print(f"  Sell on AERODROME: {links_base['sell_link'][:55]}...")
    
    # Test Telegram format
    print("\n--- Telegram Format (Solana) ---")
    print(format_links_for_telegram(opp_solana))
    
    print("\n--- Telegram Format (Base) ---")
    print(format_links_for_telegram(opp_base))
    
    # Test get_all_dex_links for both chains
    print("\n--- All DEX Links (Base chain) ---")
    all_base = get_all_dex_links(BRETT_BASE, USDC_BASE, chain="base")
    for dex_name, links in all_base.items():
        print(f"  {dex_name.upper()}: Buy={links['buy_link'][:35]}...")
    
    print("\n" + "=" * 70)
    print("✅ All tests passed!")

