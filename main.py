# main.py
# El punt d'entrada: s'executa amb  python main.py
#
# 1. Llegeix la configuració (si és la primera vegada, demana la clau de Gemini).
# 2. Crea l'assistent i la finestra.
# 3. Engega l'assistent i mostra la finestra.

import sys

from PyQt6.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

try:
    # El navegador del globus terraqüi s'ha d'importar abans de crear la QApplication
    import PyQt6.QtWebEngineWidgets  # noqa: F401
except ImportError:
    pass

from assistent import Assistent
from config import carregar_config, desar_config
from interficie import FinestraPrincipal


def demanar_configuracio_inicial(config):
    """La primera vegada, demana la clau API i el nom de l'usuari."""
    clau, ok = QInputDialog.getText(
        None, "Configuració inicial",
        "Enganxa la teva clau API de Gemini\n(la pots treure gratis a aistudio.google.com/apikey):",
        QLineEdit.EchoMode.Password)
    if not ok or not clau.strip():
        return False
    config["api_key"] = clau.strip()

    nom, ok = QInputDialog.getText(
        None, "Configuració inicial",
        "Com et dius? (ho pots deixar en blanc)")
    if ok:
        config["nom_usuari"] = nom.strip()

    desar_config(config)
    return True


def main():
    app = QApplication(sys.argv)
    config = carregar_config()

    if not config["api_key"]:
        if not demanar_configuracio_inicial(config):
            QMessageBox.warning(None, "Falta la clau",
                                "Sense la clau API de Gemini l'assistent no pot funcionar.")
            return

    assistent = Assistent(config)
    finestra = FinestraPrincipal(config, assistent)
    finestra.show()
    finestra.afegir_missatge("sys", "Iniciant l'assistent…")
    assistent.iniciar()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
