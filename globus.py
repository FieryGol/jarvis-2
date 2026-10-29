# globus.py
# El panell del globus terraqüi que surt al mig de la finestra (on hi ha el
# reactor), com al JARVIS de les pel·lícules. Dins hi ha un navegador petit
# (QtWebEngine) que carrega globus.html, i Python li dona ordres amb JavaScript:
# volar a un lloc, canviar de mode (holograma o satèl·lit), tornar a l'inici...
#
# Si la biblioteca PyQt6-WebEngine no hi és, disponible() torna False i el
# plugin terra obre Google Earth al navegador.

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

try:
    from PyQt6.QtWebEngineCore import QWebEngineSettings
    from PyQt6.QtWebEngineWidgets import QWebEngineView
except ImportError:
    QWebEngineView = None


def disponible():
    return QWebEngineView is not None


def _fitxer_html():
    # Dins del JARVIS2.exe, els fitxers que porta a dins són a sys._MEIPASS
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base / "globus.html"


class PanellGlobus(QWidget):
    def __init__(self, finestra):
        super().__init__()
        from interficie import Colors, color     # aquí dins: interficie.py també importa aquest fitxer
        self.finestra = finestra
        self.carregat = False
        self.pendents = []             # ordres que arriben abans que la pàgina estigui a punt
        self.mode = "holograma"

        columna = QVBoxLayout(self)
        columna.setContentsMargins(14, 12, 14, 12)
        columna.setSpacing(8)

        fila = QHBoxLayout()
        fila.addWidget(finestra._etiqueta("◈ LA TERRA", 9, Colors.PRINCIPAL, negreta=True))
        fila.addStretch()
        self.boto_mode = self._boto("🛰  SATÈL·LIT", Colors.PRINCIPAL, self.canviar_mode)
        fila.addWidget(self.boto_mode)
        fila.addWidget(self._boto("🌍  INICI", Colors.PRINCIPAL, lambda: self.executar("jarvis.inici()")))
        fila.addWidget(self._boto("✕  TANCA", Colors.VERMELL, lambda: finestra.mostrar_globus(False)))
        columna.addLayout(fila)

        self.vista = QWebEngineView()
        ajustos = self.vista.settings()
        # globus.html és un fitxer local que carrega Cesium i les imatges d'Internet
        ajustos.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        ajustos.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        self.vista.page().setBackgroundColor(color(Colors.FONS))
        self.vista.loadFinished.connect(self._carregat)
        self.vista.load(QUrl.fromLocalFile(str(_fitxer_html())))
        self.vista.setStyleSheet(f"border: 1px solid {Colors.PRINCIPAL};")
        columna.addWidget(self.vista, 1)

    def _boto(self, text, color, accio):
        boto = QPushButton(text)
        boto.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        boto.setStyleSheet(self.finestra._estil_boto(color))
        boto.clicked.connect(accio)
        return boto

    def _carregat(self, ok):
        self.carregat = ok
        if ok:
            for js in self.pendents:
                self.vista.page().runJavaScript(js)
            self.pendents.clear()

    def executar(self, js):
        """Executa una ordre de JavaScript a la pàgina (o la guarda si encara s'està carregant)."""
        if self.carregat:
            self.vista.page().runJavaScript(js)
        else:
            self.pendents.append(js)

    def posar_mode(self, mode):
        self.mode = "satel·lit" if mode == "satel·lit" else "holograma"
        self.executar(f"jarvis.mode({json.dumps(self.mode)})")
        self.boto_mode.setText("💠  HOLOGRAMA" if self.mode == "satel·lit" else "🛰  SATÈL·LIT")

    def canviar_mode(self):
        self.posar_mode("holograma" if self.mode == "satel·lit" else "satel·lit")

    def ordre(self, dades):
        """Les ordres que envia el plugin terra (des de la conversa)."""
        if dades.get("mode"):
            self.posar_mode(dades["mode"])
        accio = dades.get("accio")
        if accio == "volar":
            self.executar(f"jarvis.volar({dades['lat']}, {dades['lon']}, {dades['alcada']}, "
                          f"{json.dumps(dades.get('nom', ''))})")
        elif accio == "inici":
            self.executar("jarvis.inici()")
        elif accio == "iss":
            self.executar("jarvis.anarIss()")
