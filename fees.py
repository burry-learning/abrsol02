# fees.py
"""
Module de calcul des frais réseau réalistes pour Solana et Base.

Fournit des estimations dynamiques des frais de transaction basées sur:
- Solana: estimation lamports par transaction
- Base: estimation gas * gasPrice en ETH
"""

import os
from typing import Optional
from utils import logger


# ============================================================================
# CONSTANTES DE BASE
# ============================================================================

# Solana - estimation moyenne des frais en lamports
SOLANA_BASE_FEE_LAMPORTS = 5000  # Fee de base Solana
SOLANA_PRIORITY_FEE_LAMPORTS = 10000  # Fee de priorité estimé
SOLANA_TOTAL_FEE_LAMPORTS = SOLANA_BASE_FEE_LAMPORTS + SOLANA_PRIORITY_FEE_LAMPORTS

# Conversion SOL/USD (estimé, devrait être dynamique dans production)
SOL_PRICE_USD = 150.0  # Prix SOL en USD

# Base - estimation gas
BASE_GAS_PER_SWAP = 150000  # Gas estimé par swap sur Base
BASE_GAS_PRICE_GWEI = 20  # Gas price moyen en gwei
ETH_PRICE_USD = 2500.0  # Prix ETH en USD


# ============================================================================
# FONCTIONS DE CALCUL DES FRAIS
# ============================================================================

def estimate_solana_network_fee(swap_size_usd: float = 1000.0) -> float:
    """
    Estime les frais réseau Solana en pourcentage du swap.

    Args:
        swap_size_usd: Taille du swap en USD

    Returns:
        Frais réseau en pourcentage décimal (ex: 0.0004 = 0.04%)
    """
    try:
        # Frais total en USD
        total_fee_usd = (SOLANA_TOTAL_FEE_LAMPORTS / 1_000_000_000) * SOL_PRICE_USD

        # Frais en pourcentage du swap
        fee_percentage = total_fee_usd / swap_size_usd

        # Cap à un maximum raisonnable (0.1%)
        return min(fee_percentage, 0.001)

    except Exception as e:
        logger.warning(f"[FEES] Error estimating Solana fee: {e}")
        return 0.0004  # Valeur par défaut


def estimate_base_network_fee(swap_size_usd: float = 1000.0) -> float:
    """
    Estime les frais réseau Base en pourcentage du swap.

    Args:
        swap_size_usd: Taille du swap en USD

    Returns:
        Frais réseau en pourcentage décimal (ex: 0.001 = 0.1%)
    """
    try:
        # Calcul gas en ETH
        gas_cost_eth = (BASE_GAS_PER_SWAP * BASE_GAS_PRICE_GWEI * 1e-9)

        # Conversion en USD
        gas_cost_usd = gas_cost_eth * ETH_PRICE_USD

        # Frais en pourcentage du swap
        fee_percentage = gas_cost_usd / swap_size_usd

        # Cap à un maximum raisonnable (0.5%)
        return min(fee_percentage, 0.005)

    except Exception as e:
        logger.warning(f"[FEES] Error estimating Base fee: {e}")
        return 0.001  # Valeur par défaut


def estimate_network_fee(
    chain: str,
    swap_size_usd: float = 1000.0
) -> float:
    """
    Estime les frais réseau pour une chaîne donnée.

    Args:
        chain: "solana" ou "base"
        swap_size_usd: Taille du swap en USD

    Returns:
        Frais réseau en pourcentage décimal
    """
    if chain.lower() == "solana":
        return estimate_solana_network_fee(swap_size_usd)
    elif chain.lower() == "base":
        return estimate_base_network_fee(swap_size_usd)
    else:
        logger.warning(f"[FEES] Unknown chain '{chain}', using Solana fees")
        return estimate_solana_network_fee(swap_size_usd)


# ============================================================================
# CONFIGURATION DYNAMIQUE
# ============================================================================

def update_price_feeds(sol_price: Optional[float] = None, eth_price: Optional[float] = None):
    """
    Met à jour les prix pour des estimations plus précises.

    Args:
        sol_price: Nouveau prix SOL/USD
        eth_price: Nouveau prix ETH/USD
    """
    global SOL_PRICE_USD, ETH_PRICE_USD

    if sol_price is not None and sol_price > 0:
        SOL_PRICE_USD = sol_price
        logger.info(f"[FEES] Updated SOL price to ${SOL_PRICE_USD}")

    if eth_price is not None and eth_price > 0:
        ETH_PRICE_USD = eth_price
        logger.info(f"[FEES] Updated ETH price to ${ETH_PRICE_USD}")


# ============================================================================
# UTILITIES
# ============================================================================

def get_fee_breakdown(chain: str, swap_size_usd: float = 1000.0) -> dict:
    """
    Retourne un breakdown détaillé des frais.

    Args:
        chain: "solana" ou "base"
        swap_size_usd: Taille du swap en USD

    Returns:
        Dict avec détails des frais
    """
    fee_pct = estimate_network_fee(chain, swap_size_usd)
    fee_usd = fee_pct * swap_size_usd

    return {
        "chain": chain,
        "swap_size_usd": swap_size_usd,
        "network_fee_pct": fee_pct,
        "network_fee_usd": fee_usd,
        "fee_source": "estimated"
    }
