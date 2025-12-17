"""Script pour recuperer le prix SOL depuis tous les DEX et envoyer sur Telegram

SOLANA DEX (4):
- Jupiter (avec API key)
- Raydium (public)
- Orca (public)
- Meteora (public)

BASE DEX (1):
- KyberSwap (public)
"""
import asyncio
import aiohttp
import os
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

# Solana tokens
SOL = "So11111111111111111111111111111111111111112"
USDC_SOL = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Base tokens (WETH pour test)
WETH_BASE = "0x4200000000000000000000000000000000000006"
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

API_KEY = os.getenv("JUPITER_API_KEY", "e539d399-9946-4a59-a074-28f4912bbdf3")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def get_prices():
    prices = {}
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(timeout=timeout) as s:
        
        # RAYDIUM (fonctionne sans API key)
        try:
            url = f"https://api-v3.raydium.io/mint/price?mints={SOL}"
            r = await s.get(url)
            if r.status == 200:
                data = await r.json()
                price = data.get("data", {}).get(SOL)
                if price:
                    prices["Raydium"] = float(price)
                    print(f"Raydium: {float(price):.4f} USDC")
        except Exception as e:
            print(f"Raydium error: {e}")
        
        # JUPITER (avec API key)
        try:
            url = f"https://api.jup.ag/swap/v1/quote?inputMint={SOL}&outputMint={USDC_SOL}&amount=1000000000"
            headers = {"x-api-key": API_KEY}
            r = await s.get(url, headers=headers)
            if r.status == 200:
                data = await r.json()
                out_amount = int(data.get("outAmount", 0))
                if out_amount > 0:
                    price = out_amount / 1_000_000  # USDC has 6 decimals
                    prices["Jupiter"] = price
                    print(f"Jupiter: {price:.4f} USDC")
            else:
                print(f"Jupiter status: {r.status}")
        except Exception as e:
            print(f"Jupiter error: {e}")
        
        # ORCA (via whirlpool - prend le pool avec le plus de TVL)
        try:
            url = "https://api.mainnet.orca.so/v1/whirlpool/list"
            r = await s.get(url)
            if r.status == 200:
                data = await r.json()
                pools = data.get("whirlpools", [])
                sol_usdc_pools = []
                for pool in pools:
                    ta = pool.get("tokenA", {})
                    tb = pool.get("tokenB", {})
                    if ta.get("mint") == SOL and tb.get("mint") == USDC_SOL:
                        tvl = float(pool.get("tvl", 0))
                        price = float(pool.get("price", 0))
                        sol_usdc_pools.append({"tvl": tvl, "price": price})
                
                if sol_usdc_pools:
                    best = max(sol_usdc_pools, key=lambda x: x["tvl"])
                    prices["Orca"] = best["price"]
                    print(f"Orca: {best['price']:.4f} USDC (TVL: ${best['tvl']:,.0f})")
        except Exception as e:
            print(f"Orca error: {e}")
        
        # METEORA (DLMM - utilise current_price avec underscore!)
        try:
            url = "https://dlmm-api.meteora.ag/pair/all"
            r = await s.get(url)
            if r.status == 200:
                data = await r.json()
                sol_usdc_pools = []
                for pool in data:
                    mx = pool.get("mint_x", "")
                    my = pool.get("mint_y", "")
                    price = pool.get("current_price")  # underscore!
                    liq = float(pool.get("liquidity", 0) or 0)
                    
                    if price and liq > 1000:
                        if mx == SOL and my == USDC_SOL:
                            sol_usdc_pools.append({"liq": liq, "price": float(price)})
                        elif mx == USDC_SOL and my == SOL:
                            sol_usdc_pools.append({"liq": liq, "price": 1.0 / float(price)})
                
                if sol_usdc_pools:
                    best = max(sol_usdc_pools, key=lambda x: x["liq"])
                    prices["Meteora"] = best["price"]
                    print(f"Meteora: {best['price']:.4f} USDC (Liq: ${best['liq']:,.0f})")
        except Exception as e:
            print(f"Meteora error: {e}")
    
    return prices


async def get_base_prices():
    """Recupere les prix sur Base chain"""
    prices = {}
    timeout = aiohttp.ClientTimeout(total=15)
    
    async with aiohttp.ClientSession(timeout=timeout) as s:
        
        # KYBERSWAP (Base) - Prix ETH en USDC
        try:
            # 1 ETH = 1e18 wei
            amount_in = "1000000000000000000"
            url = f"https://aggregator-api.kyberswap.com/base/api/v1/routes?tokenIn={WETH_BASE}&tokenOut={USDC_BASE}&amountIn={amount_in}"
            r = await s.get(url)
            if r.status == 200:
                data = await r.json()
                route_summary = data.get("data", {}).get("routeSummary", {})
                amount_out = route_summary.get("amountOut", "0")
                if amount_out and int(amount_out) > 0:
                    # USDC has 6 decimals
                    price = int(amount_out) / 1_000_000
                    prices["KyberSwap"] = price
                    print(f"KyberSwap (Base ETH): {price:.4f} USDC")
            else:
                print(f"KyberSwap status: {r.status}")
        except Exception as e:
            print(f"KyberSwap error: {e}")
    
    return prices

async def send_telegram(solana_prices, base_prices):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram not configured")
        return
    
    now = datetime.now(timezone.utc).strftime("%d/%m/%Y %H:%M:%S UTC")
    
    lines = [
        "\U0001F4CA *PRIX DEX - MULTI-CHAIN*",
        f"_{now}_",
        "",
    ]
    
    # Section Solana
    if solana_prices:
        lines.append("\u26D3 *SOLANA - SOL/USDC*")
        sorted_prices = sorted(solana_prices.items(), key=lambda x: x[1], reverse=True)
        max_p = max(solana_prices.values())
        min_p = min(solana_prices.values())
        
        for dex, price in sorted_prices:
            if price == max_p:
                emoji = "\U0001F534"
            elif price == min_p:
                emoji = "\U0001F7E2"
            else:
                emoji = "\u26AA"
            lines.append(f"{emoji} *{dex}*: `${price:.4f}`")
        
        spread = ((max_p - min_p) / min_p) * 100
        lines.append(f"\U0001F4C8 Spread: `{spread:.3f}%`")
        lines.append(f"\U0001F7E2 Buy: *{min(solana_prices, key=solana_prices.get)}*")
        lines.append(f"\U0001F534 Sell: *{max(solana_prices, key=solana_prices.get)}*")
        lines.append("")
    
    # Section Base
    if base_prices:
        lines.append("\U0001F535 *BASE - ETH/USDC*")
        for dex, price in base_prices.items():
            lines.append(f"\u26AA *{dex}*: `${price:.4f}`")
        lines.append("")
    
    # Stats globales
    total_dex = len(solana_prices) + len(base_prices)
    lines.append(f"\U0001F4CA *Total DEX*: {total_dex}")
    
    text = "\n".join(lines)
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as session:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
        }
        async with session.post(url, json=payload) as resp:
            if resp.status == 200:
                print("[OK] Message envoye sur Telegram!")
            else:
                error = await resp.text()
                print(f"[ERROR] Telegram: {error}")

async def main():
    print("=" * 50)
    print("=== SOLANA DEX ===")
    solana_prices = await get_prices()
    print(f"Solana: {len(solana_prices)} DEX")
    
    print()
    print("=== BASE DEX ===")
    base_prices = await get_base_prices()
    print(f"Base: {len(base_prices)} DEX")
    
    print()
    print("=" * 50)
    total = len(solana_prices) + len(base_prices)
    print(f"Total: {total} DEX")
    print()
    
    await send_telegram(solana_prices, base_prices)

if __name__ == "__main__":
    asyncio.run(main())

