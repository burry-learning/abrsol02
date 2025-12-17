# utils.py
"""
Utilitaires et helpers pour le bot d'arbitrage.

Contient:
- Configuration du logging
- Fonctions helpers pour dates/timestamps
- Formatters pour affichage
"""
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# ============================================================================
# Configuration du Logging
# ============================================================================

def setup_logger(name: str = "arbbot", level: str = None) -> logging.Logger:
    """
    Configure le logger avec handlers console + fichier.
    
    Args:
        name: Nom du logger
        level: Niveau de log (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Logger configuré
    """
    # Niveau depuis env ou défaut INFO
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level, logging.INFO))
    
    # Éviter les handlers dupliqués
    if logger.handlers:
        return logger
    
    # Format des logs
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Handler console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler fichier (si activé)
    save_logs = os.getenv("SAVE_LOGS", "true").lower() == "true"
    if save_logs:
        log_file = os.getenv("LOG_FILE", "logs/arbitrage_bot.log")
        
        # Créer le dossier logs si nécessaire
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Logging to file: {log_file}")
    
    return logger

# Logger global
logger = setup_logger()

# ============================================================================
# Fonctions Utilitaires
# ============================================================================

def now_ts() -> int:
    """Retourne le timestamp Unix actuel"""
    return int(datetime.utcnow().timestamp())

def format_timestamp(ts: float = None) -> str:
    """
    Formate un timestamp en chaîne lisible.
    
    Args:
        ts: Timestamp Unix (ou None pour maintenant)
    
    Returns:
        Chaîne formatée "YYYY-MM-DD HH:MM:SS"
    """
    if ts is None:
        dt = datetime.utcnow()
    else:
        dt = datetime.utcfromtimestamp(ts)
    return dt.strftime("%Y-%m-%d %H:%M:%S")

def format_percentage(value: float, decimals: int = 2) -> str:
    """
    Formate un décimal en pourcentage.
    
    Args:
        value: Valeur décimale (0.05 = 5%)
        decimals: Nombre de décimales
    
    Returns:
        Chaîne formatée "5.00%"
    """
    return f"{value * 100:.{decimals}f}%"

def format_usd(value: float, decimals: int = 2) -> str:
    """
    Formate une valeur en USD.
    
    Args:
        value: Montant en USD
        decimals: Nombre de décimales
    
    Returns:
        Chaîne formatée "$1,234.56"
    """
    return f"${value:,.{decimals}f}"

def truncate_address(address: str, start: int = 8, end: int = 4) -> str:
    """
    Tronque une adresse Solana pour l'affichage.
    
    Args:
        address: Adresse complète
        start: Nombre de caractères au début
        end: Nombre de caractères à la fin
    
    Returns:
        Adresse tronquée "So111111...1112"
    """
    if len(address) <= start + end:
        return address
    return f"{address[:start]}...{address[-end:]}"

def calculate_profit_usd(spread_net: float, investment_usd: float = 1000.0) -> float:
    """
    Calcule le profit estimé en USD.
    
    Args:
        spread_net: Spread net après frais (décimal)
        investment_usd: Montant investi en USD
    
    Returns:
        Profit estimé en USD
    """
    return spread_net * investment_usd

# ============================================================================
# Validation
# ============================================================================

def is_valid_solana_address(address: str) -> bool:
    """
    Vérifie si une adresse Solana est valide (validation basique).
    
    Args:
        address: Adresse à vérifier
    
    Returns:
        True si valide, False sinon
    """
    if not address or not isinstance(address, str):
        return False
    
    # Les adresses Solana font 32-44 caractères en base58
    if len(address) < 32 or len(address) > 44:
        return False
    
    # Caractères valides en base58 (sans 0, O, I, l)
    valid_chars = set("123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz")
    return all(c in valid_chars for c in address)
