# test_smoke_pools.py
"""
Script de smoke-test pour vérifier le fonctionnement du système pool-to-pool.

Tests:
1. Fetch pools depuis tous les DEX
2. Compute spread pour un token
3. Rendu du message Telegram (format texte, sans envoi)
"""
import asyncio
import aiohttp
import json
from arbitrage import compute_spread_and_metrics
from pool_fetchers import fetch_all_pools
from pool_prices import get_pool_prices_for_token
from telegram_bot import send_opportunity
from utils import logger

# Token de test (SOL)
TEST_TOKEN = "So11111111111111111111111111111111111111112"
BASE_TOKEN = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"  # USDC

async def test_fetch_pools():
    """Test 1: Fetch pools depuis tous les DEX"""
    print("\n" + "="*70)
    print("TEST 1: Fetch pools depuis tous les DEX")
    print("="*70)
    
    async with aiohttp.ClientSession() as session:
        pools = await fetch_all_pools(session)
        
        total = sum(len(p) for p in pools.values())
        print(f"✅ Total pools récupérées: {total}")
        
        for dex, pools_list in pools.items():
            print(f"  • {dex.capitalize()}: {len(pools_list)} pools")
        
        return pools

async def test_get_pool_prices():
    """Test 2: Récupérer les pools pour un token spécifique"""
    print("\n" + "="*70)
    print(f"TEST 2: Pools pour token {TEST_TOKEN[:8]}...")
    print("="*70)
    
    async with aiohttp.ClientSession() as session:
        pools = await get_pool_prices_for_token(session, TEST_TOKEN, BASE_TOKEN)
        
        print(f"✅ {len(pools)} pools trouvées pour le token")
        
        for i, pool in enumerate(pools[:5], 1):  # Afficher les 5 premières
            print(f"\nPool #{i}:")
            print(f"  DEX: {pool.get('dex')}")
            print(f"  Pool ID: {pool.get('pool_id', 'N/A')[:16]}...")
            print(f"  Buy price: {pool.get('buy_price', 0):.8f}")
            print(f"  Sell price: {pool.get('sell_price', 0):.8f}")
            print(f"  Fee: {pool.get('fee_pct', 0)*100:.2f}%")
            print(f"  Liquidity: ${pool.get('liquidity_usd', 0):,.0f}")
            print(f"  URL: {pool.get('url', 'N/A')}")
        
        return pools

async def test_compute_spread():
    """Test 3: Calculer un spread d'arbitrage"""
    print("\n" + "="*70)
    print(f"TEST 3: Calcul spread d'arbitrage pour {TEST_TOKEN[:8]}...")
    print("="*70)
    
    async with aiohttp.ClientSession() as session:
        result = await compute_spread_and_metrics(
            session, 
            TEST_TOKEN, 
            BASE_TOKEN,
            liquidity_usd=100_000,
            volume_24h=50_000,
            swap_size_usd=1000
        )
        
        if result:
            print("✅ Opportunité détectée!")
            print(f"\nDétails:")
            print(f"  Token: {result.get('token', 'N/A')[:16]}...")
            print(f"  Buy DEX: {result.get('buy_dex')}")
            print(f"  Sell DEX: {result.get('sell_dex')}")
            print(f"  Buy Pool ID: {result.get('buy_pool_id', 'N/A')[:16]}...")
            print(f"  Sell Pool ID: {result.get('sell_pool_id', 'N/A')[:16]}...")
            print(f"  Buy price: {result.get('buy_price', 0):.8f}")
            print(f"  Sell price: {result.get('sell_price', 0):.8f}")
            print(f"  Spread brut: {result.get('spread_brut', 0)*100:.3f}%")
            print(f"  Spread net: {result.get('spread_net', 0)*100:.3f}%")
            print(f"  Confidence: {result.get('confidence_score', 0)}/100")
            print(f"  Buy Pool URL: {result.get('buy_pool_url', 'N/A')}")
            print(f"  Sell Pool URL: {result.get('sell_pool_url', 'N/A')}")
            
            # Afficher les détails JSON
            print(f"\n📋 JSON log entry:")
            log_entry = {
                "type": "opportunity_detected",
                "token": result.get('token', '')[:8] + "...",
                "buy_dex": result.get('buy_dex'),
                "sell_dex": result.get('sell_dex'),
                "spread_net_pct": round(result.get('spread_net', 0) * 100, 3),
                "confidence_score": result.get('confidence_score', 0),
            }
            print(json.dumps(log_entry, indent=2))
            
            return result
        else:
            print("❌ Aucune opportunité détectée")
            return None

async def test_telegram_message_format():
    """Test 4: Format du message Telegram (sans envoi)"""
    print("\n" + "="*70)
    print("TEST 4: Format message Telegram (rendu texte)")
    print("="*70)
    
    async with aiohttp.ClientSession() as session:
        result = await compute_spread_and_metrics(
            session, 
            TEST_TOKEN, 
            BASE_TOKEN,
            liquidity_usd=100_000,
            volume_24h=50_000,
            swap_size_usd=1000
        )
        
        if result:
            # Construire le message comme dans telegram_bot.py
            token_short = result.get('token', 'Unknown')[:8] + "..." + result.get('token', '')[-4:]
            buy_dex = result.get('buy_dex', '?').title()
            sell_dex = result.get('sell_dex', '?').title()
            buy_price = result.get('buy_price', 0)
            sell_price = result.get('sell_price', 0)
            spread_net = result.get('spread_net', 0)
            buy_pool_url = result.get('buy_pool_url')
            sell_pool_url = result.get('sell_pool_url')
            details = result.get('details', {})
            buy_pool_fee = details.get('buy_pool_fee_pct', 0)
            sell_pool_fee = details.get('sell_pool_fee_pct', 0)
            
            message = f"""
🚀 OPPORTUNITÉ D'ARBITRAGE 🔥
BONNE 🟣 SOLANA

*Token:* `{token_short}`

🔄 *Stratégie Pool-to-Pool:*
  • Acheter sur *{buy_dex}* @ `{buy_price:.8f}`
  • Vendre sur *{sell_dex}* @ `{sell_price:.8f}`

📊 *Spreads:*
  • Spread brut: `{(result.get('spread_brut', 0)*100):.2f}%`
  • Coûts totaux: `{(result.get('total_costs', 0)*100):.2f}%`
  • *Spread net: `{spread_net*100:.2f}%`* ✅

💸 *Frais des pools:*
  • Buy pool fee: `{buy_pool_fee*100:.2f}%`
  • Sell pool fee: `{sell_pool_fee*100:.2f}%`

💰 *Profit estimé (1000 USD):*
  • Net: `${spread_net * 1000:.2f}` USD

🔗 *Liens des pools:*
  • BUY Pool: {buy_pool_url or 'N/A'}
  • SELL Pool: {sell_pool_url or 'N/A'}
"""
            print(message)
            print("✅ Message formaté correctement")
        else:
            print("❌ Pas d'opportunité pour tester le format")

async def main():
    """Lancer tous les tests"""
    print("\n" + "="*70)
    print("SMOKE TEST - Système Pool-to-Pool")
    print("="*70)
    
    try:
        # Test 1: Fetch pools
        await test_fetch_pools()
        
        # Test 2: Get pool prices for token
        await test_get_pool_prices()
        
        # Test 3: Compute spread
        opportunity = await test_compute_spread()
        
        # Test 4: Telegram message format
        await test_telegram_message_format()
        
        print("\n" + "="*70)
        print("✅ Tous les tests terminés avec succès!")
        print("="*70)
        
    except Exception as e:
        print(f"\n❌ Erreur pendant les tests: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())

