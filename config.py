# config.py
# Guarda i llegeix la configuració de l'assistent en un fitxer JSON.
# Així la clau de Gemini i els noms no s'han de tornar a escriure cada vegada.

import json
import sys
from pathlib import Path

# El fitxer es guarda a la mateixa carpeta que el programa. Si és el JARVIS.exe
# (fet amb PyInstaller), a la carpeta on hi ha l'.exe.
if getattr(sys, "frozen", False):
    CARPETA = Path(sys.executable).parent
else:
    CARPETA = Path(__file__).parent
FITXER_CONFIG = CARPETA / "config.json"

# Valors per defecte (els que es fan servir la primera vegada)
CONFIG_PER_DEFECTE = {
    "api_key": "",
    "nom_assistent": "JARVIS",
    "nom_usuari": "",
    "veu": "Charon",          # veus de Gemini: Charon, Puck, Kore, Fenrir, Aoede
    # Com de fort has de parlar per interrompre'l mentre parla (de 0 a 1).
    # Si s'interromp sol amb la seva pròpia veu, puja-ho; si costa tallar-lo, baixa-ho.
    "sensibilitat_interrupcio": 0.15,
    # Demanar permís abans d'esborrar, enviar, tancar programes, apagar...
    "confirmar_perilloses": True,
    # Poder respondre la confirmació dient «sí» o «no» en veu alta (a més de la finestra)
    "confirmar_per_veu": True,
    # Noms dels plugins (fitxers de plugins/ sense .py) que no s'han de carregar
    "plugins_desactivats": [],
}


def carregar_config():
    """Llegeix config.json. Si no existeix o està malmès, torna els valors per defecte."""
    config = dict(CONFIG_PER_DEFECTE)
    fitxers = [FITXER_CONFIG]
    # El JARVIS.exe pot portar una configuració a dins (amb la clau). Si al costat
    # de l'.exe hi ha un config.json, aquest té preferència.
    if getattr(sys, "frozen", False):
        fitxers.insert(0, Path(sys._MEIPASS) / "config.json")
    for fitxer in fitxers:
        if fitxer.exists():
            try:
                with open(fitxer, "r", encoding="utf-8") as f:
                    config.update(json.load(f))
            except Exception as e:
                print(f"[Config] No s'ha pogut llegir {fitxer.name}: {e}")
    return config


def desar_config(config):
    """Escriu la configuració a config.json."""
    with open(FITXER_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
