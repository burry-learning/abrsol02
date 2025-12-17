#!/usr/bin/env python3
"""
Script pour lancer uniquement le dashboard web sans le bot de trading.
Utile pour accéder à l'interface sans démarrer la détection d'arbitrage.
"""
import sys
import os

# Ajouter le répertoire courant au path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import run_ui_server

if __name__ == "__main__":
    print("=" * 60)
    print("DEMARRAGE DU DASHBOARD WEB")
    print("=" * 60)
    print()
    print("Acces au dashboard: http://localhost:8000")
    print("Pour arreter: Ctrl+C")
    print()
    print("=" * 60)
    print()
    
    try:
        run_ui_server(host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        print("\nDashboard arrete.")
    except Exception as e:
        print(f"\nErreur: {e}")
        sys.exit(1)

