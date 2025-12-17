# token_loader.py
"""
Module de chargement et validation des tokens surveillés.

Charge depuis tokens.json avec validation d'adresses blockchain.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from utils import logger


# ============================================================================
# VALIDATION D'ADRESSES
# ============================================================================

def is_valid_solana_address(address: str) -> bool:
    """
    Validation basique d'adresse Solana.
    Les adresses Solana font 32-44 caractères en base58.
    """
    if not address or not isinstance(address, str):
        return False

    if len(address) < 32 or len(address) > 44:
        return False

    # Caractères valides en base58 (sans 0, O, I, l)
    valid_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    return all(c in valid_chars for c in address)


def is_valid_ethereum_address(address: str) -> bool:
    """
    Validation basique d'adresse Ethereum/Base.
    Les adresses Ethereum commencent par 0x et font 42 caractères.
    """
    if not address or not isinstance(address, str):
        return False

    if not address.startswith("0x") or len(address) != 42:
        return False

    # Caractères hexadécimaux uniquement
    try:
        int(address[2:], 16)
        return True
    except ValueError:
        return False


def validate_address(address: str, chain: str) -> bool:
    """Valide une adresse selon la chaîne."""
    if chain.lower() == "solana":
        return is_valid_solana_address(address)
    elif chain.lower() == "base":
        return is_valid_ethereum_address(address)
    else:
        return False


# ============================================================================
# CHARGEMENT DES TOKENS
# ============================================================================

def load_tokens_from_file(file_path: str = "tokens.json") -> Dict[str, List[Dict]]:
    """
    Charge les tokens depuis un fichier JSON avec validation.

    Args:
        file_path: Chemin vers le fichier tokens.json

    Returns:
        Dict avec clés "solana" et "base", valeurs = listes de tokens validés
    """
    tokens_path = Path(file_path)

    if not tokens_path.exists():
        logger.error(f"[TOKENS] File not found: {file_path}")
        return {"solana": [], "base": []}

    try:
        with open(tokens_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        validated_tokens = {"solana": [], "base": []}

        for chain in ["solana", "base"]:
            if chain not in data:
                logger.warning(f"[TOKENS] Chain '{chain}' not found in {file_path}")
                continue

            chain_data = data[chain]
            if "tokens" not in chain_data:
                logger.warning(f"[TOKENS] 'tokens' key missing for chain '{chain}'")
                continue

            for token in chain_data["tokens"]:
                address = token.get("address", "")
                symbol = token.get("symbol", "UNKNOWN")
                category = token.get("category", "unknown")

                if not validate_address(address, chain):
                    logger.warning(
                        f"[TOKENS] Invalid {chain} address for {symbol}: {address}"
                    )
                    continue

                validated_tokens[chain].append({
                    "address": address,
                    "symbol": symbol,
                    "category": category,
                    "chain": chain
                })

        logger.info(
            f"[TOKENS] Loaded {len(validated_tokens['solana'])} Solana + "
            f"{len(validated_tokens['base'])} Base tokens"
        )

        return validated_tokens

    except json.JSONDecodeError as e:
        logger.error(f"[TOKENS] Invalid JSON in {file_path}: {e}")
        return {"solana": [], "base": []}
    except Exception as e:
        logger.error(f"[TOKENS] Error loading tokens: {e}")
        return {"solana": [], "base": []}


# ============================================================================
# GETTERS CONVENIENCE
# ============================================================================

def get_solana_tokens() -> List[str]:
    """Retourne la liste des adresses Solana."""
    tokens = load_tokens_from_file()
    return [t["address"] for t in tokens["solana"]]


def get_base_tokens() -> List[str]:
    """Retourne la liste des adresses Base."""
    tokens = load_tokens_from_file()
    return [t["address"] for t in tokens["base"]]


def get_all_tokens() -> List[str]:
    """Retourne toutes les adresses tokens."""
    tokens = load_tokens_from_file()
    return get_solana_tokens() + get_base_tokens()


def get_token_info(address: str, chain: str = None) -> Optional[Dict]:
    """
    Retourne les informations d'un token par son adresse.

    Args:
        address: Adresse du token
        chain: Chaîne ("solana" ou "base"), si None teste les deux

    Returns:
        Dict avec symbol, category, chain ou None si non trouvé
    """
    tokens = load_tokens_from_file()

    chains_to_check = [chain] if chain else ["solana", "base"]

    for chain_name in chains_to_check:
        for token in tokens[chain_name]:
            if token["address"] == address:
                return token.copy()

    return None


# ============================================================================
# FILTRES PAR CATÉGORIE
# ============================================================================

def get_tokens_by_category(chain: str, category: str) -> List[str]:
    """
    Retourne les adresses des tokens d'une catégorie spécifique.

    Args:
        chain: "solana" ou "base"
        category: "bluechip", "meme", "defi", "stable", etc.
    """
    tokens = load_tokens_from_file()
    return [
        t["address"] for t in tokens.get(chain, [])
        if t.get("category") == category
    ]


def get_high_priority_tokens(chain: str) -> List[str]:
    """
    Tokens prioritaires (bluechip + stables).
    """
    return get_tokens_by_category(chain, "bluechip") + get_tokens_by_category(chain, "stable")
