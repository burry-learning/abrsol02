# config.py
from dotenv import load_dotenv
import os

load_dotenv()

# ============================================================
# TELEGRAM
# ============================================================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = int(os.getenv("TELEGRAM_CHAT_ID", "5454546249"))

# ============================================================
# API KEYS
# ============================================================
JUPITER_API_KEY = os.getenv("JUPITER_API_KEY", "e539d399-9946-4a59-a074-28f4912bbdf3")

# ============================================================
# SOLANA DEX ENDPOINTS (6)
# ============================================================
# NOTE: Ces endpoints sont utilisés pour les prix agrégés (ancien système)
# Le nouveau système utilise les endpoints POOLS ci-dessous
JUPITER_PRICE_API = "https://api.jup.ag/price/v2"
JUPITER_QUOTE_API = os.getenv("JUPITER_QUOTE_API", "https://quote-api.jup.ag/v6/quote")
RAYDIUM_API = "https://api-v3.raydium.io"
ORCA_API = "https://api.mainnet.orca.so"
METEORA_API = "https://dlmm-api.meteora.ag"
PHOENIX_API = "https://api.phoenix.so"
LIFINITY_API = "https://lifinity.io/api"

# ============================================================
# SOLANA DEX POOLS ENDPOINTS (nouveau système pool-to-pool)
# ============================================================
# Ces endpoints peuvent être configurés via .env si nécessaire
RAYDIUM_POOLS_API = os.getenv("RAYDIUM_POOLS_API", "https://api.raydium.io/v2/amm/pools")
ORCA_WHIRLPOOLS_API = os.getenv("ORCA_WHIRLPOOLS_API", "https://api.mainnet.orca.so/v1/whirlpool/list")
METEORA_POOLS_API = os.getenv("METEORA_POOLS_API", "https://dlmm-api.meteora.ag/pools")
PHOENIX_MARKETS_API = os.getenv("PHOENIX_MARKETS_API", "https://api.phoenix.so/v1/markets")
LIFINITY_POOLS_API = os.getenv("LIFINITY_POOLS_API", "https://lifinity.io/api/getPools")

# ============================================================
# BASE DEX ENDPOINTS (4)
# ============================================================
# Ces endpoints peuvent être configurés via .env si nécessaire
UNISWAP_QUOTE_API = os.getenv("UNISWAP_QUOTE_API", "https://api.uniswap.org/v1/quote")
AERODROME_QUOTE_API = os.getenv("AERODROME_QUOTE_API", "https://api.aerodrome.finance/swap/quote")
AERODROME_POOLS_API = os.getenv("AERODROME_POOLS_API", "https://api.aerodrome.finance/api/v1/pools")
PANCAKESWAP_QUOTE_API = os.getenv("PANCAKESWAP_QUOTE_API", "https://pancakeswap.finance/api/v1/quote")
KYBERSWAP_BASE_API = os.getenv("KYBERSWAP_BASE_API", "https://aggregator-api.kyberswap.com/base/api/v1/routes")

# ============================================================
# RPC ENDPOINTS (Configurables)
# ============================================================
# ⚠️ IMPORTANT: Les RPC publics sont lents et limités en rate
# Pour production, utiliser un RPC dédié (Helius, QuickNode, etc.)
# Ces variables peuvent être modifiées dans .env selon vos besoins

# Solana RPC endpoint - utilisé pour les requêtes blockchain Solana
SOLANA_RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.triton.one")

# Base RPC endpoint - utilisé pour les requêtes blockchain Base
BASE_RPC_URL = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")

# Backward compatibility (anciens noms)
RPC_ENDPOINT = SOLANA_RPC_URL
BASE_RPC_ENDPOINT = BASE_RPC_URL

# ============================================================
# FILTERS AND THRESHOLDS
# ============================================================
# Interval between scans
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "30"))

# Minimum time between two alerts pour une même paire (capé à 60s)
_min_notif_env = int(os.getenv("MIN_NOTIFICATION_INTERVAL_SECONDS", "60"))
MIN_NOTIFICATION_INTERVAL_SECONDS = min(_min_notif_env, 60)

# Minimum spread after fees (0.0025 = 0.25%)
try:
    MIN_SPREAD_AFTER_FEES = float(os.getenv("MIN_SPREAD_AFTER_FEES", "0.0025"))
except (ValueError, TypeError):
    # Fallback en cas d'erreur de conversion
    MIN_SPREAD_AFTER_FEES = 0.0025

# Minimum liquidity
MIN_LIQUIDITY_USD = float(os.getenv("MIN_LIQUIDITY_USD", "50000"))

# Minimum 24h volume
MIN_VOLUME_24H = float(os.getenv("MIN_VOLUME_24H", "100000"))
