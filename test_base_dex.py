#!/usr/bin/env python3
"""
Test script for Base chain DEX price fetchers.

Tests:
- Uniswap V3
- Aerodrome Finance
- PancakeSwap V3
- KyberSwap

Run: python test_base_dex.py
"""
import asyncio
import aiohttp
import sys

# Add project root to path
sys.path.insert(0, ".")

from base_dex_fetchers import (
    get_uniswap_price,
    get_aerodrome_price,
    get_pancakeswap_price,
    get_kyberswap_price,
    get_all_base_dex_prices,
    evaluate_base_arbitrage,
    estimate_base_slippage,
    calculate_base_mev_penalty,
    get_base_swap_url,
    WETH_BASE,
    USDC_BASE,
    BASE_DEX_FEES,
)
from dex_links import get_swap_link, get_arbitrage_links


# Popular Base tokens for testing
WETH = WETH_BASE
USDC = USDC_BASE
BRETT = "0x532f27101965dd16442E59d40670FaF5eBB142E4"  # BRETT - popular memecoin
TOSHI = "0xAC1Bd2486aAf3B5C0fc3Fd868558b082a531B2B4"  # TOSHI
DEGEN = "0x4ed4E862860beD51a9570b96d89aF5E1B0Efefed"  # DEGEN


async def test_individual_dex():
    """Test each DEX individually."""
    print("=" * 70)
    print("TEST: Individual Base DEX Price Fetchers")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        # Test with WETH -> USDC
        print(f"\n[INFO] Testing WETH -> USDC quote")
        print(f"   WETH: {WETH}")
        print(f"   USDC: {USDC}")
        print()
        
        # Uniswap V3
        print("[DEX] Uniswap V3...")
        try:
            result = await get_uniswap_price(session, WETH, USDC)
            if result:
                print(f"   [OK] Price: ${result.get('price', 'N/A'):.2f}")
                print(f"      Fee tier: {result.get('fee_tier', 'N/A')}")
                print(f"      Fee %: {result.get('fee_decimal', 0)*100:.2f}%")
            else:
                print("   [FAIL] No result")
        except Exception as e:
            print(f"   [ERROR] {e}")
        
        # Aerodrome
        print("\n[DEX] Aerodrome Finance...")
        try:
            result = await get_aerodrome_price(session, WETH, USDC)
            if result:
                print(f"   [OK] Price: ${result.get('price', 'N/A'):.2f}")
                print(f"      Fee %: {result.get('fee_decimal', 0)*100:.2f}%")
                print(f"      Stable: {result.get('is_stable', 'N/A')}")
            else:
                print("   [FAIL] No result")
        except Exception as e:
            print(f"   [ERROR] {e}")
        
        # PancakeSwap
        print("\n[DEX] PancakeSwap V3...")
        try:
            result = await get_pancakeswap_price(session, WETH, USDC)
            if result:
                print(f"   [OK] Price: ${result.get('price', 'N/A'):.2f}")
                print(f"      Fee tier: {result.get('fee_tier', 'N/A')}")
                print(f"      Fee %: {result.get('fee_decimal', 0)*100:.2f}%")
            else:
                print("   [FAIL] No result")
        except Exception as e:
            print(f"   [ERROR] {e}")
        
        # KyberSwap
        print("\n[DEX] KyberSwap...")
        try:
            result = await get_kyberswap_price(session, WETH, USDC)
            if result:
                print(f"   [OK] Price: ${result.get('price', 'N/A'):.2f}")
                print(f"      Fee %: {result.get('fee_decimal', 0)*100:.2f}%")
            else:
                print("   [FAIL] No result")
        except Exception as e:
            print(f"   [ERROR] {e}")


async def test_batch_fetch():
    """Test batch fetching from all DEX."""
    print("\n" + "=" * 70)
    print("TEST: Batch Fetch All Base DEX")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        print(f"\n[INFO] Fetching WETH prices from all 4 DEX...")
        
        all_prices = await get_all_base_dex_prices(session, WETH, USDC)
        
        print("\nResults:")
        for dex, data in all_prices.items():
            if data:
                print(f"   [OK] {dex.upper():12}: ${data.get('price', 0):.2f}")
            else:
                print(f"   [--] {dex.upper():12}: No data")


async def test_arbitrage_evaluation():
    """Test arbitrage evaluation for Base chain."""
    print("\n" + "=" * 70)
    print("TEST: Base Arbitrage Evaluation")
    print("=" * 70)
    
    async with aiohttp.ClientSession() as session:
        tokens = [WETH, BRETT]
        
        for token in tokens:
            print(f"\n[INFO] Evaluating token: {token[:10]}...")
            
            result = await evaluate_base_arbitrage(
                session,
                token,
                USDC,
                min_spread=0.001  # 0.1% for testing
            )
            
            if result:
                print(f"   [OK] Opportunity found!")
                print(f"      Buy: {result['buy_dex'].upper()} @ ${result['buy_price']:.6f}")
                print(f"      Sell: {result['sell_dex'].upper()} @ ${result['sell_price']:.6f}")
                print(f"      Spread brut: {result['spread_brut']*100:.2f}%")
                print(f"      Spread net: {result['spread_net']*100:.3f}%")
                print(f"      Confidence: {result['confidence']}/100")
                print(f"      Profit ($1000): ${result['profit_estimate_usd']:.2f}")
                print(f"      Buy URL: {result['buy_url'][:50]}...")
                print(f"      Sell URL: {result['sell_url'][:50]}...")
            else:
                print("   [--] No opportunity (spread too low or not enough DEX)")


def test_slippage_and_mev():
    """Test slippage and MEV calculations."""
    print("\n" + "=" * 70)
    print("TEST: Slippage & MEV Calculations")
    print("=" * 70)
    
    print("\n[INFO] Slippage estimates by liquidity:")
    liq_levels = [2_000_000, 500_000, 100_000, 15_000]
    for liq in liq_levels:
        slip = estimate_base_slippage(liq)
        print(f"   ${liq:>10,}: {slip*100:.2f}%")
    
    print("\n[INFO] MEV penalty by liquidity:")
    for liq in liq_levels:
        mev = calculate_base_mev_penalty(liq)
        print(f"   ${liq:>10,}: {mev*100:.2f}%")


def test_swap_urls():
    """Test swap URL generation for Base DEX."""
    print("\n" + "=" * 70)
    print("TEST: Base DEX Swap URL Generation")
    print("=" * 70)
    
    print("\n[INFO] Swap URLs (WETH -> USDC):")
    dexes = ["uniswap", "aerodrome", "pancakeswap", "kyberswap"]
    
    for dex in dexes:
        url = get_swap_link(dex, WETH, USDC, chain="base")
        print(f"   {dex.upper():12}: {url[:60]}...")
    
    print("\n[INFO] Arbitrage links test:")
    opp = {
        "buy_dex": "aerodrome",
        "sell_dex": "uniswap",
        "token": BRETT,
        "base": USDC,
        "chain": "base"
    }
    links = get_arbitrage_links(opp)
    print(f"   Buy on AERODROME:  {links['buy_link'][:55]}...")
    print(f"   Sell on UNISWAP:   {links['sell_link'][:55]}...")


def test_fee_table():
    """Display Base DEX fee table."""
    print("\n" + "=" * 70)
    print("TEST: Base DEX Fee Table")
    print("=" * 70)
    
    print("\n[INFO] DEX Fees:")
    for dex, fee in BASE_DEX_FEES.items():
        print(f"   {dex.upper():12}: {fee*100:.2f}%")


async def main():
    """Run all tests."""
    print("\n" + "=" * 70)
    print("BASE CHAIN DEX INTEGRATION TESTS")
    print("=" * 70)
    
    # Run synchronous tests
    test_fee_table()
    test_slippage_and_mev()
    test_swap_urls()
    
    # Run async tests
    await test_individual_dex()
    await test_batch_fetch()
    await test_arbitrage_evaluation()
    
    print("\n" + "=" * 70)
    print("[SUCCESS] All tests completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())

