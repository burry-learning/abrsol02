"""
thegraph_fetcher.py

Helpers pour interroger des subgraphs TheGraph pour récupérer des pools
Raydium/Orca/Meteora (Solana - si subgraph dispo) et Uniswap V3 / Aerodrome /
PancakeSwap (Base). La fonction principale `get_pool_from_subgraph` retourne
la pool avec la plus grande TVL pour un pair token0/token1.

Note: certains DEX Solana n'ont pas toujours de subgraph public fiable; ce
module reste best-effort.
"""
import asyncio
import os
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

import aiohttp

from utils import logger

# Proxies (optionnel, pour réseaux bloqués)
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

# Subgraph endpoints (best-effort / publics)
SUBGRAPHS = {
    "solana": {
        # Best-effort / exemples (peuvent être indisponibles)
        "raydium": "https://api.raydium.io/subgraph",  # placeholder
        "orca": "https://api.mainnet.orca.so/v1/graphql",  # placeholder (non-thegraph)
        "meteora": "https://graph.meteora.ag/subgraphs/name/meteora/pools",  # placeholder
    },
    "base": {
        # Studio endpoints (plus récents) - peuvent nécessiter un token si privé
        "uniswap_v3": "https://api.studio.thegraph.com/query/24660/uniswap-v3-base/version/latest",
        "aerodrome": "https://api.studio.thegraph.com/query/45376/aerodrome-v2/version/latest",
        "pancake_v3": "https://api.studio.thegraph.com/query/1951/pancakeswap-v3-base/version/latest",
    },
}


def sqrt_price_x96_to_price(sqrt_price_x96: float, dec0: int, dec1: int) -> Optional[float]:
    try:
        p = (float(sqrt_price_x96) / (2 ** 96)) ** 2
        adjust = 10 ** (dec0 - dec1)
        return p * adjust
    except Exception:
        return None


async def query_subgraph(
    session: aiohttp.ClientSession,
    subgraph_url: str,
    query: str,
    variables: dict,
    timeout: int = 15
) -> Optional[dict]:
    """
    Query TheGraph subgraph avec support proxy et validation stricte.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    for attempt in range(3):
        try:
            async with session.post(
                subgraph_url,
                json={"query": query, "variables": variables},
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Subgraph returned {resp.status}: {subgraph_url}")
                    await asyncio.sleep(1 * (2 ** attempt))
                    continue

                data = await resp.json()

                if not data:
                    logger.error(f"Empty response from {subgraph_url}")
                    return None
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    return None
                if "data" not in data:
                    logger.error(f"No 'data' field in response from {subgraph_url}")
                    return None
                return data

        except asyncio.TimeoutError:
            logger.warning(f"Timeout querying {subgraph_url}")
        except aiohttp.ClientError as e:
            logger.warning(f"Network error querying {subgraph_url}: {e}")
        except Exception as e:
            logger.exception(f"Unexpected error querying {subgraph_url}: {e}")

        await asyncio.sleep(1 * (2 ** attempt))

    return None


async def query_pools_generic(
    session: aiohttp.ClientSession,
    url: str,
    token0: str,
    token1: str,
    dex: str
) -> List[Dict[str, Any]]:
    query = """
    query Pools($token0: Bytes!, $token1: Bytes!) {
      pools(
        where: {
          token0_in: [$token0, $token1],
          token1_in: [$token0, $token1]
        },
        first: 20,
        orderBy: totalValueLockedUSD,
        orderDirection: desc
      ) {
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
    payload = {"query": query, "variables": {"token0": token0.lower(), "token1": token1.lower()}}
    data = await query_subgraph(session, url, query, {"token0": token0.lower(), "token1": token1.lower()}, timeout=20)
    if not data:
        return []
    try:
        return data.get("data", {}).get("pools", []) or []
    except Exception as e:
        logger.debug(f"[{dex}] parse error: {e}")
        return []


async def normalize_pools(pools: List[Dict[str, Any]], token: str, dex: str, chain: str) -> Optional[Dict[str, Any]]:
    """
    Sélectionne la pool avec la plus grande TVL et normalise buy/sell price.
    """
    best = None
    best_tvl = 0.0
    for p in pools:
        try:
            pid = p.get("id")
            t0 = p.get("token0", {})
            t1 = p.get("token1", {})
            dec0 = int(t0.get("decimals", 18))
            dec1 = int(t1.get("decimals", 18))
            sqrt_px = float(p.get("sqrtPrice") or 0)
            price = sqrt_price_x96_to_price(sqrt_px, dec0, dec1)
            tvl = float(p.get("totalValueLockedUSD", 0) or 0)
            if not pid or not price or price <= 0 or tvl <= 0:
                continue
            token0_addr = t0.get("id")
            token1_addr = t1.get("id")
            if token.lower() not in (token0_addr.lower(), token1_addr.lower()):
                continue
            # buy/sell selon la position
            buy_price = price if token.lower() == token1_addr.lower() else 1 / price
            sell_price = 1 / price if token.lower() == token1_addr.lower() else price
            fee_bps = int(p.get("feeTier", 0) or 3000)
            fee_pct = max(0.0, min(fee_bps / 10000.0, 0.05))
            if tvl > best_tvl:
                best_tvl = tvl
                best = {
                    "token": token,
                    "pool_id": pid,
                    "dex": dex,
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "fee_pct": fee_pct,
                    "liquidity_usd": tvl,
                    "url": f"https://app.uniswap.org/explore/pools/{chain}/{pid}" if dex == "uniswap_v3" else f"https://pancakeswap.finance/info/v3/pool/{pid}" if dex == "pancake_v3" else pid,
                    "chain": chain,
                }
        except Exception as e:
            logger.debug(f"[{dex}] normalize error: {e}")
            continue
    return best


async def get_pool_from_subgraph(
    session: aiohttp.ClientSession,
    token0: str,
    token1: str,
    dex: str,
    chain: str
) -> Optional[Dict[str, Any]]:
    """
    Interroge le subgraph du DEX/chain, retourne la pool avec la plus grande TVL pour token0/token1.
    """
    url = SUBGRAPHS.get(chain, {}).get(dex)
    if not url:
        logger.warning(f"No subgraph URL for chain={chain}, dex={dex}")
        return None

    pools = await query_pools_generic(session, url, token0, token1, dex)
    if not pools:
        return None
    best = await normalize_pools(pools, token0, dex, chain)
    return best


# ============================================================================
# Static fallback
# ============================================================================
_static_pools_cache: Optional[dict] = None


def load_static_pools() -> dict:
    """Charge les pools statiques depuis data/static_pools.json"""
    global _static_pools_cache

    if _static_pools_cache is not None:
        return _static_pools_cache

    static_file = Path(__file__).parent / "data" / "static_pools.json"
    if not static_file.exists():
        logger.warning(f"Static pools file not found: {static_file}")
        return {"base": {}, "solana": {}}

    try:
        with open(static_file, "r") as f:
            _static_pools_cache = json.load(f)
            logger.info(f"Loaded static pools from {static_file}")
            return _static_pools_cache
    except Exception as e:
        logger.error(f"Error loading static pools: {e}")
        return {"base": {}, "solana": {}}


def get_static_pools_for_pair(
    token0: str,
    token1: str,
    chain: str = "base"
) -> List[Dict[str, Any]]:
    """
    Récupère les pools statiques pour une paire (ordre indifférent).
    """
    static_data = load_static_pools()
    chain_data = static_data.get(chain, {})

    pair_key1 = f"{token0}/{token1}"
    pair_key2 = f"{token1}/{token0}"

    pools_raw = chain_data.get(pair_key1) or chain_data.get(pair_key2) or []
    pools = []
    for pool_raw in pools_raw:
        try:
            pools.append({
                "token": token0,
                "pool_id": pool_raw["pool_id"],
                "dex": pool_raw["dex"],
                "buy_price": pool_raw["price"],
                "sell_price": pool_raw["price"],
                "fee_pct": pool_raw["fee_pct"],
                "liquidity_usd": pool_raw["liquidity_usd"],
                "url": pool_raw.get("swap_url") or "",
                "chain": chain,
                "source": "static"
            })
        except Exception as e:
            logger.debug(f"Error parsing static pool: {e}")
            continue

    if pools:
        logger.info(f"Using {len(pools)} static pools for {token0[:8]}/{token1[:8]}")

    return pools

# --------------------------------------------------------------------------- #
# Test main
# --------------------------------------------------------------------------- #
async def _test():
    # Example: WETH/USDC on Base via Uniswap V3 subgraph
    WETH = "0x4200000000000000000000000000000000000006"
    USDC = "0x833589fcd6edb6e08f4c7c19962234ef8f82f18e"
    async with aiohttp.ClientSession() as session:
        res = await get_pool_from_subgraph(session, WETH, USDC, "uniswap_v3", "base")
        print(res)


def main():
    asyncio.run(_test())


if __name__ == "__main__":
    main()

