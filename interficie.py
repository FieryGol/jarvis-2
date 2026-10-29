# interficie.py
# Tot el que es veu: la finestra, el reactor del mig, el monitor del sistema,
# l'agenda d'avui, el registre d'activitat i la finestra de confirmació de les
# accions perilloses. Fet amb PyQt6.
#
# Hi ha tres classes:
#   - Reactor:          el cercle animat del centre (canvia segons l'estat).
#   - BarraMetrica:     cada barra del monitor del sistema (CPU, memòria...).
#   - FinestraPrincipal: la finestra que ho junta tot.

import html
import math
import time
from datetime import datetime

import psutil
from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap,
                         QRadialGradient, QShortcut)
from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox,
                             QPushButton, QSizePolicy, QSystemTrayIcon, QTextEdit,
                             QVBoxLayout, QWidget)

import eines

FONT = "Consolas"


# Colors de tota la interfície
class Colors:
    FONS = "#00060a"
    PANELL = "#010d14"
    VORA = "#0d3347"
    PRINCIPAL = "#00d4ff"
    TENUE = "#007a99"
    TEXT = "#8ffcff"
    TEXT_TENUE = "#3a8a9a"
    BLANC = "#d8f8ff"
    TARONJA = "#ff6b00"
    GROC = "#ffcc00"
    VERD = "#00ff88"
    VERMELL = "#ff3355"


# Color i velocitat de gir del reactor per a cada estat
ESTATS = {
    "CONNECTANT":   (Colors.TENUE, 0.6),
    "DESCONNECTAT": (Colors.VERMELL, 0.2),
    "ESCOLTANT":    (Colors.PRINCIPAL, 1.0),
    "PENSANT":      (Colors.GROC, 4.0),
    "PARLANT":      (Colors.TARONJA, 2.0),
    "SILENCIAT":    (Colors.VERMELL, 0.3),
}


def color(hex_color, alfa=255):
    """Crea un QColor a partir d'un text com "#00d4ff" i una transparència (0-255)."""
    c = QColor(hex_color)
    c.setAlpha(alfa)
    return c


# ─────────────────────────────────────────────────────────────────────────────
#  El reactor del centre
# ─────────────────────────────────────────────────────────────────────────────

class Reactor(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 320)
        self.estat = "CONNECTANT"
        self.angle = 0.0
        self.nivell = 0.0             # el volum que ens arriba (0 a 1)
        self.nivell_mostrat = 0.0     # el que dibuixem (es mou suaument cap a nivell)

        # Un temporitzador redibuixa el reactor 30 vegades per segon
        self.temporitzador = QTimer(self)
        self.temporitzador.timeout.connect(self._pas)
        self.temporitzador.start(33)

    def posar_estat(self, estat):
        self.estat = estat

    def posar_nivell(self, nivell):
        self.nivell = nivell

    def _pas(self):
        _, velocitat = ESTATS.get(self.estat, (Colors.PRINCIPAL, 1.0))
        self.angle = (self.angle + velocitat) % 360
        # Ens apropem una mica al nivell real a cada pas, així no fa salts
        self.nivell_mostrat += (self.nivell - self.nivell_mostrat) * 0.3
        self.nivell *= 0.9            # si no arriba so nou, va baixant sol
        self.update()                 # demana a Qt que torni a cridar paintEvent

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        principal, _ = ESTATS.get(self.estat, (Colors.PRINCIPAL, 1.0))
        cx = self.width() / 2
        cy = self.height() / 2 - 15
        r = min(self.width(), self.height() - 40) * 0.42

        # 1. Cercle exterior amb marques, com un rellotge
        p.setPen(QPen(color(Colors.VORA), 1))
        p.drawEllipse(QPointF(cx, cy), r, r)
        for i in range(60):
            a = math.radians(i * 6)
            llarg = 10 if i % 5 == 0 else 4
            x1 = cx + math.cos(a) * r
            y1 = cy + math.sin(a) * r
            x2 = cx + math.cos(a) * (r - llarg)
            y2 = cy + math.sin(a) * (r - llarg)
            p.setPen(QPen(color(principal, 140 if i % 5 == 0 else 60), 1))
            p.drawLine(QPointF(x1, y1), QPointF(x2, y2))

        # 2. Arcs que giren (Qt mesura els angles en setzens de grau)
        self._arcs(p, cx, cy, r * 0.86, 3, self.angle, 70, color(principal, 200), 3)
        self._arcs(p, cx, cy, r * 0.72, 4, -self.angle * 1.5, 40, color(principal, 120), 2)
        self._arcs(p, cx, cy, r * 0.60, 2, self.angle * 0.7, 120, color(principal, 70), 1)

        # 3. El nucli: un cercle brillant que creix amb el volum de la veu
        nucli = r * 0.32 * (1 + 0.35 * self.nivell_mostrat)
        degradat = QRadialGradient(QPointF(cx, cy), nucli * 1.8)
        degradat.setColorAt(0.0, color(Colors.BLANC, 255))
        degradat.setColorAt(0.25, color(principal, 230))
        degradat.setColorAt(0.6, color(principal, 60))
        degradat.setColorAt(1.0, color(principal, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(degradat)
        p.drawEllipse(QPointF(cx, cy), nucli * 1.8, nucli * 1.8)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(color(principal, 220), 2))
        p.drawEllipse(QPointF(cx, cy), nucli, nucli)

        # 4. El text de l'estat, sota el cercle
        p.setPen(color(principal))
        p.setFont(QFont(FONT, 11, QFont.Weight.Bold))
        punt = "●" if int(time.time() * 2) % 2 == 0 else "○"   # parpelleja
        p.drawText(QRectF(0, cy + r + 10, self.width(), 30),
                   Qt.AlignmentFlag.AlignCenter, f"{punt}  {self.estat}")

    def _arcs(self, p, cx, cy, radi, quantitat, angle_inici, llargada, pen_color, gruix):
        """Dibuixa uns quants arcs repartits al voltant d'un cercle."""
        p.setPen(QPen(pen_color, gruix))
        quadrat = QRectF(cx - radi, cy - radi, radi * 2, radi * 2)
        separacio = 360 / quantitat
        for i in range(quantitat):
            inici = angle_inici + i * separacio
            p.drawArc(quadrat, int(inici * 16), int(llargada * 16))


# ─────────────────────────────────────────────────────────────────────────────
#  Barres del monitor del sistema
# ─────────────────────────────────────────────────────────────────────────────

class BarraMetrica(QWidget):
    def __init__(self, nom, color_barra):
        super().__init__()
        self.nom = nom
        self.color_barra = color_barra
        self.valor = 0.0          # de 0 a 100
        self.setFixedHeight(32)

    def posar_valor(self, valor):
        self.valor = max(0.0, min(100.0, valor))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        amplada = self.width()

        # Nom a l'esquerra i valor a la dreta
        p.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        p.setPen(color(Colors.TEXT_TENUE))
        p.drawText(QRectF(0, 0, amplada, 16), Qt.AlignmentFlag.AlignLeft, self.nom)
        p.setPen(color(self.color_barra))
        p.drawText(QRectF(0, 0, amplada, 16), Qt.AlignmentFlag.AlignRight, f"{self.valor:.0f}%")

        # La barra: el fons i la part plena
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color(Colors.VORA))
        p.drawRoundedRect(QRectF(0, 19, amplada, 6), 3, 3)
        p.setBrush(color(self.color_barra))
        p.drawRoundedRect(QRectF(0, 19, amplada * self.valor / 100, 6), 3, 3)


# ─────────────────────────────────────────────────────────────────────────────
#  La finestra principal
# ─────────────────────────────────────────────────────────────────────────────

class FinestraPrincipal(QMainWindow):
    def __init__(self, config, assistent):
        super().__init__()
        self.config = config
        self.assistent = assistent
        nom = config["nom_assistent"]

        self.setWindowTitle(f"{nom} — Assistent de veu")
        self.resize(1000, 680)
        self.setMinimumSize(860, 560)
        self.setStyleSheet(f"background: {Colors.FONS}; color: {Colors.TEXT};")

        # Estructura: capçalera a dalt, tres columnes al mig i peu a baix
        central = QWidget()
        columna = QVBoxLayout(central)
        columna.setContentsMargins(0, 0, 0, 0)
        columna.setSpacing(0)
        columna.addWidget(self._crear_capcalera(nom))

        mig = QHBoxLayout()
        mig.setContentsMargins(0, 0, 0, 0)
        mig.setSpacing(0)
        mig.addWidget(self._crear_panell_esquerre())
        # Al centre hi ha el reactor i el panell de la càmera. Només se'n veu un:
        # quan s'obre la càmera, amaguem el reactor.
        self.reactor = Reactor()
        self.panell_camera = self._crear_panell_camera()
        self.panell_camera.hide()
        mig.addWidget(self.reactor, 1)          # el "1" fa que ocupi l'espai que sobra
        mig.addWidget(self.panell_camera, 1)
        # El globus terraqüi es crea la primera vegada que es fa servir (tarda un moment)
        self.mig = mig
        self.panell_globus = None
        mig.addWidget(self._crear_panell_dret())
        columna.addLayout(mig, 1)

        columna.addWidget(self._crear_peu())
        self.setCentralWidget(central)

        # Dreceres de teclat
        QShortcut(QKeySequence("F4"), self).activated.connect(self._canviar_silenci)
        QShortcut(QKeySequence("F11"), self).activated.connect(self._pantalla_completa)
        QShortcut(QKeySequence("Esc"), self).activated.connect(self.assistent.interrompre)

        # Connectem els senyals de l'assistent amb la finestra
        self.assistent.missatge.connect(self.afegir_missatge)
        self.assistent.canvi_estat.connect(self.reactor.posar_estat)
        self.assistent.nivell.connect(self.reactor.posar_nivell)
        self.assistent.canvi_estat.connect(self._estat_a_la_camera)
        self.assistent.camera_visible.connect(self._mostrar_camera)
        self.assistent.camera.nou_frame.connect(self._nova_imatge)
        self.assistent.confirmacio.connect(self._confirmar)
        self.assistent.notificacio.connect(self._notificar)
        self.assistent.eines_canviades.connect(self._actualitzar_eines)
        self.assistent.ordre_interficie.connect(self._ordre_interficie)

        # Icona a la barra de tasques per a les notificacions de Windows (recordatoris)
        self.icona = QSystemTrayIcon(self._crear_icona(), self)
        self.icona.setToolTip(nom)
        self.icona.show()
        self.setWindowIcon(self.icona.icon())

        # Rellotge i monitor del sistema s'actualitzen sols
        self.temporitzador = QTimer(self)
        self.temporitzador.timeout.connect(self._actualitzar_monitor)
        self.temporitzador.start(1500)
        self._actualitzar_monitor()

        # L'agenda d'avui, cada 30 segons
        self.temporitzador_agenda = QTimer(self)
        self.temporitzador_agenda.timeout.connect(self._actualitzar_agenda)
        self.temporitzador_agenda.start(30000)
        self._actualitzar_agenda()

    # ── Peces de la finestra ─────────────────────────────────────────────────

    def _etiqueta(self, text, mida=8, color_text=Colors.TEXT_TENUE, negreta=False):
        """Crea un QLabel amb el nostre estil (per no repetir codi)."""
        etiqueta = QLabel(text)
        pes = QFont.Weight.Bold if negreta else QFont.Weight.Normal
        etiqueta.setFont(QFont(FONT, mida, pes))
        etiqueta.setStyleSheet(f"color: {color_text}; background: transparent;")
        return etiqueta

    def _estil_boto(self, color_text):
        return (f"QPushButton {{ background: {Colors.PANELL}; color: {color_text};"
                f" border: 1px solid {Colors.VORA}; border-radius: 3px; padding: 6px; }}"
                f"QPushButton:hover {{ border: 1px solid {color_text}; }}")

    def _crear_capcalera(self, nom):
        capcalera = QWidget()
        capcalera.setFixedHeight(56)
        capcalera.setStyleSheet(f"background: {Colors.PANELL}; border-bottom: 1px solid {Colors.VORA};")
        fila = QHBoxLayout(capcalera)
        fila.setContentsMargins(16, 4, 16, 4)

        fila.addWidget(self._etiqueta(self.config.get("nom_usuari", ""), 8, Colors.TENUE))
        fila.addStretch()

        titols = QVBoxLayout()
        titols.setSpacing(0)
        titol = self._etiqueta(nom.upper(), 17, Colors.PRINCIPAL, negreta=True)
        titol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitol = self._etiqueta("Assistent personal d'IA · v2", 7, Colors.TEXT_TENUE)
        subtitol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        titols.addWidget(titol)
        titols.addWidget(subtitol)
        fila.addLayout(titols)

        fila.addStretch()
        self.rellotge = self._etiqueta("00:00:00", 12, Colors.PRINCIPAL, negreta=True)
        fila.addWidget(self.rellotge)
        return capcalera

    def _crear_panell_esquerre(self):
        panell = QWidget()
        panell.setFixedWidth(200)
        panell.setStyleSheet(f"background: {Colors.PANELL}; border-right: 1px solid {Colors.VORA};")
        columna = QVBoxLayout(panell)
        columna.setContentsMargins(12, 12, 12, 12)
        columna.setSpacing(8)

        columna.addWidget(self._etiqueta("◈ MONITOR DEL SISTEMA", 8, Colors.PRINCIPAL, negreta=True))
        self.barra_cpu = BarraMetrica("CPU", Colors.PRINCIPAL)
        self.barra_mem = BarraMetrica("MEMÒRIA", Colors.GROC)
        self.barra_disc = BarraMetrica("DISC", Colors.VERD)
        self.barra_bat = BarraMetrica("BATERIA", Colors.TARONJA)
        for barra in (self.barra_cpu, self.barra_mem, self.barra_disc, self.barra_bat):
            columna.addWidget(barra)

        columna.addSpacing(6)
        self.etiqueta_actiu = self._etiqueta("ACTIU  --:--")
        self.etiqueta_proc = self._etiqueta("PROCESSOS  --")
        columna.addWidget(self.etiqueta_actiu)
        columna.addWidget(self.etiqueta_proc)

        columna.addSpacing(10)
        columna.addWidget(self._etiqueta("◈ AGENDA D'AVUI", 8, Colors.PRINCIPAL, negreta=True))
        self.etiqueta_agenda = self._etiqueta("Res més per avui.", 8, Colors.TEXT)
        self.etiqueta_agenda.setWordWrap(True)
        self.etiqueta_agenda.setAlignment(Qt.AlignmentFlag.AlignTop)
        columna.addWidget(self.etiqueta_agenda)
        columna.addStretch()

        self.etiqueta_nucli = self._etiqueta("NUCLI IA\nACTIU", 7, Colors.VERD, negreta=True)
        self.etiqueta_nucli.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.etiqueta_nucli.setStyleSheet(f"color: {Colors.VERD}; border: 1px solid {Colors.VORA};"
                                          f" border-radius: 3px; padding: 4px;")
        columna.addWidget(self.etiqueta_nucli)
        return panell

    def _crear_panell_dret(self):
        panell = QWidget()
        panell.setFixedWidth(330)
        panell.setStyleSheet(f"background: {Colors.PANELL}; border-left: 1px solid {Colors.VORA};")
        columna = QVBoxLayout(panell)
        columna.setContentsMargins(10, 10, 10, 10)
        columna.setSpacing(6)

        columna.addWidget(self._etiqueta("▸ REGISTRE D'ACTIVITAT", 8, Colors.PRINCIPAL, negreta=True))
        self.registre = QTextEdit()
        self.registre.setReadOnly(True)
        self.registre.setFont(QFont(FONT, 9))
        self.registre.setStyleSheet(f"background: {Colors.FONS}; border: 1px solid {Colors.VORA};"
                                    f" border-radius: 3px; padding: 4px;")
        columna.addWidget(self.registre, 1)

        columna.addWidget(self._etiqueta("▸ ENTRADA D'ORDRES", 8, Colors.PRINCIPAL, negreta=True))
        fila = QHBoxLayout()
        self.entrada = QLineEdit()
        self.entrada.setPlaceholderText("Escriu una ordre o una pregunta…")
        self.entrada.setFont(QFont(FONT, 9))
        self.entrada.setStyleSheet(f"background: {Colors.FONS}; color: {Colors.BLANC};"
                                   f" border: 1px solid {Colors.VORA}; border-radius: 3px; padding: 5px;")
        self.entrada.returnPressed.connect(self._enviar)
        boto_enviar = QPushButton("▸")
        boto_enviar.setFixedWidth(34)
        boto_enviar.setStyleSheet(self._estil_boto(Colors.PRINCIPAL))
        boto_enviar.clicked.connect(self._enviar)
        fila.addWidget(self.entrada)
        fila.addWidget(boto_enviar)
        columna.addLayout(fila)

        self.boto_micro = QPushButton("🎙  MICRÒFON ACTIU")
        self.boto_micro.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        self.boto_micro.setStyleSheet(self._estil_boto(Colors.VERD))
        self.boto_micro.clicked.connect(self._canviar_silenci)
        columna.addWidget(self.boto_micro)

        boto_interrompre = QPushButton("✋  INTERROMP  [ESC]")
        boto_interrompre.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        boto_interrompre.setStyleSheet(self._estil_boto(Colors.TARONJA))
        boto_interrompre.clicked.connect(self.assistent.interrompre)
        columna.addWidget(boto_interrompre)

        self.boto_camera = QPushButton("📷  OBRE LA CÀMERA")
        self.boto_camera.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        self.boto_camera.setStyleSheet(self._estil_boto(Colors.PRINCIPAL))
        self.boto_camera.clicked.connect(self.assistent.canviar_camera)
        columna.addWidget(self.boto_camera)
        return panell

    def _crear_panell_camera(self):
        panell = QWidget()
        columna = QVBoxLayout(panell)
        columna.setContentsMargins(14, 12, 14, 12)
        columna.setSpacing(8)

        fila = QHBoxLayout()
        fila.addWidget(self._etiqueta("◈ CÀMERA — EL QUE VEIG", 9, Colors.PRINCIPAL, negreta=True))
        fila.addStretch()
        self.estat_camera = self._etiqueta("", 8, Colors.TEXT_TENUE, negreta=True)
        fila.addWidget(self.estat_camera)
        boto_tancar = QPushButton("✕  TANCA")
        boto_tancar.setFont(QFont(FONT, 8, QFont.Weight.Bold))
        boto_tancar.setStyleSheet(self._estil_boto(Colors.VERMELL))
        boto_tancar.clicked.connect(self.assistent.tancar_camera)
        fila.addWidget(boto_tancar)
        columna.addLayout(fila)

        self.imatge_camera = QLabel("Obrint la càmera…")
        self.imatge_camera.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # "Ignored" evita que la imatge faci créixer la finestra cada vegada
        self.imatge_camera.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.imatge_camera.setStyleSheet(f"color: {Colors.TEXT_TENUE}; background: #000000;"
                                         f" border: 1px solid {Colors.PRINCIPAL}; border-radius: 4px;")
        columna.addWidget(self.imatge_camera, 1)
        return panell

    def _crear_peu(self):
        peu = self._etiqueta("[F4] Silencia  ·  [F11] Pantalla completa  ·  [ESC] Interromp", 7)
        peu.setAlignment(Qt.AlignmentFlag.AlignCenter)
        peu.setFixedHeight(22)
        peu.setStyleSheet(f"color: {Colors.TEXT_TENUE}; background: {Colors.PANELL};"
                          f" border-top: 1px solid {Colors.VORA};")
        return peu

    # ── El que passa quan l'usuari fa coses ──────────────────────────────────

    def _enviar(self):
        text = self.entrada.text().strip()
        if text:
            self.entrada.clear()
            self.assistent.enviar_text(text)

    def _canviar_silenci(self):
        silenciat = self.assistent.canviar_silenci()
        if silenciat:
            self.boto_micro.setText("🔇  MICRÒFON SILENCIAT")
            self.boto_micro.setStyleSheet(self._estil_boto(Colors.VERMELL))
            self.afegir_missatge("sys", "Micròfon silenciat.")
        else:
            self.boto_micro.setText("🎙  MICRÒFON ACTIU")
            self.boto_micro.setStyleSheet(self._estil_boto(Colors.VERD))
            self.afegir_missatge("sys", "Micròfon actiu.")

    def _pantalla_completa(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _mostrar_camera(self, visible):
        """Canvia el reactor pel panell de la càmera, o al revés."""
        if visible:
            self.imatge_camera.clear()
            self.imatge_camera.setText("Obrint la càmera…")
            self.mostrar_globus(False)
            self.reactor.hide()
            self.panell_camera.show()
            self.boto_camera.setText("📷  TANCA LA CÀMERA")
            self.afegir_missatge("sys", "Càmera oberta.")
        else:
            self.panell_camera.hide()
            self.reactor.show()
            self.boto_camera.setText("📷  OBRE LA CÀMERA")
            self.afegir_missatge("sys", "Càmera tancada.")

    def _ordre_interficie(self, accio, dades):
        """Coses que els plugins demanen a la finestra."""
        if accio == "globus":
            self.mostrar_globus(dades.get("accio") != "tancar")
            if dades.get("accio") != "tancar":
                self.panell_globus.ordre(dades)

    def mostrar_globus(self, visible):
        """Canvia el reactor pel globus terraqüi, o al revés."""
        if visible:
            if self.panell_globus is None:
                from globus import PanellGlobus
                self.panell_globus = PanellGlobus(self)
                self.mig.insertWidget(2, self.panell_globus, 1)
            if self.panell_camera.isVisible():
                self.assistent.tancar_camera()
            self.reactor.hide()
            self.panell_globus.show()
        elif self.panell_globus is not None and self.panell_globus.isVisible():
            self.panell_globus.hide()
            self.reactor.show()

    def _nova_imatge(self, imatge):
        """Mostra una imatge de la càmera, ajustada a la mida del panell."""
        if not self.panell_camera.isVisible():
            return
        pixmap = QPixmap.fromImage(imatge).scaled(
            self.imatge_camera.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.imatge_camera.setPixmap(pixmap)

    def _estat_a_la_camera(self, estat):
        # Mentre es veu la càmera, el reactor està amagat: posem l'estat al panell
        color_estat, _ = ESTATS.get(estat, (Colors.PRINCIPAL, 1.0))
        self.estat_camera.setText(f"●  {estat}")
        self.estat_camera.setStyleSheet(f"color: {color_estat}; background: transparent;")

    def _confirmar(self, nom, detall, resposta):
        """Pregunta a l'usuari si pot fer una acció perillosa. La resposta va al Future
        que està esperant assistent.py."""
        self.showNormal()
        self.raise_()
        self.activateWindow()
        caixa = QMessageBox(self)
        # Windows no sempre deixa passar la finestra al davant (si l'usuari és al navegador,
        # per exemple): la posem sempre a sobre i, a més, avisem amb una notificació.
        caixa.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._notificar(f"Necessito que confirmis una acció: {nom}")
        caixa.setWindowTitle(f"{self.config['nom_assistent']} vol fer una acció")
        caixa.setIcon(QMessageBox.Icon.Warning)
        caixa.setText(f"<b>Permets que faci això?</b><br><span style='color:#888'>Eina: {html.escape(nom)}</span>")
        if self.config.get("confirmar_per_veu", True):
            detall += "\n\n🎤 També pots dir «sí» o «no» en veu alta."
        caixa.setInformativeText(detall)
        si = caixa.addButton("Sí, fes-ho", QMessageBox.ButtonRole.AcceptRole)
        no = caixa.addButton("No", QMessageBox.ButtonRole.RejectRole)
        caixa.setDefaultButton(no)            # Retorn diu que no, per seguretat
        caixa.setEscapeButton(no)
        caixa.setStyleSheet(f"QMessageBox {{ background: {Colors.PANELL}; }} "
                            f"QLabel {{ color: {Colors.BLANC}; font-family: {FONT}; }} "
                            + self._estil_boto(Colors.PRINCIPAL))
        # Si l'assistent deixa d'esperar (passa el temps), tanquem la finestra
        temporitzador = QTimer(caixa)
        temporitzador.timeout.connect(lambda: resposta.done() and caixa.reject())
        temporitzador.start(500)
        caixa.exec()
        if not resposta.done():
            resposta.set_result(caixa.clickedButton() is si)

    def _notificar(self, text):
        self.icona.showMessage(self.config["nom_assistent"], text,
                               QSystemTrayIcon.MessageIcon.Information, 10000)

    def _crear_icona(self):
        """Dibuixa la icona: un cercle com el reactor."""
        pixmap = QPixmap(64, 64)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        degradat = QRadialGradient(QPointF(32, 32), 30)
        degradat.setColorAt(0.0, color(Colors.BLANC))
        degradat.setColorAt(0.4, color(Colors.PRINCIPAL))
        degradat.setColorAt(1.0, color(Colors.FONS))
        p.setBrush(degradat)
        p.setPen(QPen(color(Colors.PRINCIPAL), 3))
        p.drawEllipse(QPointF(32, 32), 28, 28)
        p.end()
        return QIcon(pixmap)

    def _actualitzar_eines(self):
        self.etiqueta_nucli.setText(f"NUCLI IA ACTIU\n{len(eines.EINES)} EINES")

    def _actualitzar_agenda(self):
        try:
            from plugins import agenda
            propers = agenda.propers(5)
        except Exception:
            self.etiqueta_agenda.setText("—")
            return
        if not propers:
            self.etiqueta_agenda.setText("Res més per avui.")
        else:
            self.etiqueta_agenda.setText("\n".join(f"{hora}  {titol}" for hora, titol in propers))

    def closeEvent(self, event):
        # Quan es tanca la finestra, deixem anar la càmera
        self.assistent.camera.tancar()
        self.icona.hide()
        super().closeEvent(event)

    # ── Coses que s'actualitzen ──────────────────────────────────────────────

    def afegir_missatge(self, tipus, text):
        """Afegeix una línia al registre, amb un color diferent per a cada tipus."""
        prefixos = {
            "tu":   ("Tu", Colors.BLANC),
            "ia":   (self.config["nom_assistent"], Colors.PRINCIPAL),
            "sys":  ("SYS", Colors.TEXT_TENUE),
            "eina": ("⚙", Colors.GROC),
            "err":  ("ERR", Colors.VERMELL),
            "avis": ("⏰", Colors.TARONJA),
        }
        prefix, color_text = prefixos.get(tipus, ("SYS", Colors.TEXT_TENUE))
        hora = datetime.now().strftime("%H:%M")
        # html.escape evita problemes si el text porta caràcters com < o >
        linia = (f'<span style="color:{Colors.TEXT_TENUE}">{hora}</span> '
                 f'<span style="color:{color_text}"><b>{html.escape(prefix)}:</b> '
                 f'{html.escape(text)}</span>')
        self.registre.append(linia)

    def _actualitzar_monitor(self):
        self.rellotge.setText(datetime.now().strftime("%H:%M:%S"))

        self.barra_cpu.posar_valor(psutil.cpu_percent(interval=None))
        self.barra_mem.posar_valor(psutil.virtual_memory().percent)
        try:
            self.barra_disc.posar_valor(psutil.disk_usage("C:\\").percent)
        except Exception:
            self.barra_disc.posar_valor(psutil.disk_usage("/").percent)
        bateria = psutil.sensors_battery()
        self.barra_bat.posar_valor(bateria.percent if bateria else 100)

        segons = time.time() - psutil.boot_time()
        hores = int(segons // 3600)
        minuts = int(segons % 3600 // 60)
        self.etiqueta_actiu.setText(f"ACTIU  {hores:02d}:{minuts:02d}")
        self.etiqueta_proc.setText(f"PROCESSOS  {len(psutil.pids())}")
