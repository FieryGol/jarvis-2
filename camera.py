# camera.py
# Llegeix la càmera web amb OpenCV, en un fil propi.
# Fa dues coses amb cada imatge:
#   - l'envia a la finestra (senyal nou_frame) perquè es vegi dins del programa;
#   - en guarda una còpia petita en JPEG perquè l'assistent la pugui enviar a Gemini.

import threading
import time

import cv2
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QImage


class Camera(QObject):
    nou_frame = pyqtSignal(QImage)    # cada imatge nova, per mostrar-la

    def __init__(self):
        super().__init__()
        self.obert = False
        self.ultim_jpeg = None        # l'última imatge, en JPEG, per a Gemini
        self.captura = None

    def obrir(self):
        """Obre la càmera. Tarda un o dos segons. Torna True si ha funcionat."""
        if self.obert:
            return True
        # CAP_DSHOW fa que a Windows s'obri més ràpid
        self.captura = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.captura.isOpened():
            self.captura = cv2.VideoCapture(0)       # provem sense, per si de cas
        if not self.captura.isOpened():
            return False

        self.obert = True
        self.ultim_jpeg = None
        threading.Thread(target=self._bucle, daemon=True).start()
        return True

    def tancar(self):
        self.obert = False            # el fil ho veurà i deixarà anar la càmera

    def _bucle(self):
        while self.obert:
            ok, imatge = self.captura.read()
            if not ok:
                time.sleep(0.05)
                continue

            # Per a Gemini: una imatge més petita, que pesa menys d'enviar
            alcada, amplada = imatge.shape[:2]
            escala = 640 / amplada
            petita = cv2.resize(imatge, (640, int(alcada * escala)))
            ok, jpeg = cv2.imencode(".jpg", petita, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ok:
                self.ultim_jpeg = jpeg.tobytes()

            # Per a la finestra: girada com un mirall (és el que esperem veure)
            # i en RGB, que és el que entén Qt (OpenCV fa servir BGR)
            mirall = cv2.flip(imatge, 1)
            rgb = cv2.cvtColor(mirall, cv2.COLOR_BGR2RGB)
            imatge_qt = QImage(rgb.data, amplada, alcada, amplada * 3,
                               QImage.Format.Format_RGB888).copy()
            self.nou_frame.emit(imatge_qt)

            time.sleep(0.03)          # unes 30 imatges per segon com a màxim

        self.captura.release()
        self.captura = None
