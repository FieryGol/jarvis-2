# assistent.py
# El "cervell" del programa: connecta amb Gemini Live, envia el que diu el
# micròfon, reprodueix la veu que torna Gemini i executa les eines.
#
# Com està organitzat (hi ha tres coses passant alhora):
#   - El MICRÒFON: sounddevice ens crida la funcio _quan_arriba_so() unes 16
#     vegades per segon amb un tros d'àudio, i nosaltres l'enviem a Gemini.
#   - L'ALTAVEU: un fil (thread) propi que va agafant l'àudio d'una cua i el
#     reprodueix.
#   - La CONNEXIÓ amb Gemini: funciona amb asyncio (programació asíncrona),
#     perquè la llibreria de Google ho fa així. Va en un altre fil perquè la
#     finestra no es quedi congelada.
#
# Les eines venen dels plugins (carpeta plugins/) i dels servidors MCP
# (mcp_servers.json). Les perilloses (esborrar, enviar, apagar...) no
# s'executen fins que l'usuari diu que sí a la finestra de confirmació.
#
# Per parlar amb la finestra fem servir "senyals" de Qt (pyqtSignal). Són
# segurs de fer servir des de qualsevol fil.

import asyncio
import concurrent.futures
import io
import json
import queue
import re
import tempfile
import threading
import time
import wave
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types
from PyQt6.QtCore import QObject, pyqtSignal

import eines
from camera import Camera
from mcp_pont import PontMCP
from reconeixement import ReconeixedorLocal

# Models de Gemini Live que provarem (si el primer falla, provem el segon)
MODELS = [
    "gemini-3.1-flash-live-preview",
    "gemini-2.5-flash-native-audio-preview-12-2025",
]

# Gemini vol l'àudio del micròfon a 16000 Hz i ens el torna a 24000 Hz
RATE_MICRO = 16000
RATE_ALTAVEU = 24000

# Durant aquest temps després que l'assistent acabi de parlar, el micròfon
# encara pot estar agafant el final de la seva veu per l'altaveu (l'"eco").
MARGE_ECO = 0.6

# Per interrompre'l parlant-li per sobre: mentre parla, només enviem el
# micròfon si el so és prou fort (més que el seu propi eco) durant uns quants
# trossos seguits. Cada tros són uns 64 ms, així que 3 trossos ≈ 0,2 segons.
TROSSOS_PER_INTERROMPRE = 3

# Cada quant enviem una imatge de la càmera a Gemini (en segons)
SEGONS_ENTRE_IMATGES = 1.0

# Quant esperem que l'usuari respongui a una confirmació (en segons)
SEGONS_PER_CONFIRMAR = 90

# Confirmar per veu: mentre la finestra de confirmació és oberta, el micròfon no va
# a Gemini Live. Gravem el que diu l'usuari, ho passem a text (primer amb el
# reconeixement de Windows i, si no ho entén clar, amb un d'aquests models) i és el
# PROGRAMA (no Gemini) qui decideix si és un sí o un no.
MODELS_TRANSCRIPCIO = ["gemini-flash-lite-latest", "gemini-flash-latest"]   # si el reconeixement de Windows no ho entén
SEGONS_TRANSCRIPCIO = 8
LLINDAR_VEU = 0.04            # volum a partir del qual considerem que l'usuari parla
TROSSOS_SILENCI_FINAL = 12    # ~0,8 s de silenci = ha acabat de parlar
TROSSOS_MAXIMS_FRASE = 95     # ~6 s com a molt per frase

PARAULES_NO = {"no", "cancel·la", "cancela", "cancel", "cancelar", "para", "atura", "nop", "stop"}
PARAULES_SI = {"sí", "si", "fes-ho", "fesho", "endavant", "confirmo", "confirmat", "d'acord",
               "vale", "adelante", "hazlo", "dale", "claro", "yes", "ok", "okay", "segur", "correcte"}


def calcular_nivell(dades):
    """Torna el volum d'un tros d'àudio entre 0 i 1 (per animar el reactor)."""
    mostres = np.frombuffer(dades, dtype=np.int16).astype(np.float32)
    if len(mostres) == 0:
        return 0.0
    rms = np.sqrt(np.mean(mostres ** 2))
    return min(1.0, rms / 6000)


def interpretar_resposta(text):
    """Decideix si el que ha dit l'usuari és un sí (True), un no (False) o no s'entén (None).
    Per seguretat, qualsevol "no" guanya, i un "sí" només val en frases curtes
    (perquè «si vols, envia-ho demà» no compti com a permís)."""
    paraules = re.findall(r"[\w·'-]+", text.lower().replace("’", "'"))
    if any(p in PARAULES_NO for p in paraules):
        return False
    if paraules and len(paraules) <= 5 and any(p in PARAULES_SI for p in paraules):
        return True
    return None


class Assistent(QObject):
    # Senyals que escolta la finestra
    missatge = pyqtSignal(str, str)   # (tipus, text). Tipus: "tu", "ia", "sys", "eina", "err", "avis"
    canvi_estat = pyqtSignal(str)     # ESCOLTANT, PENSANT, PARLANT, SILENCIAT...
    nivell = pyqtSignal(float)        # volum de 0 a 1
    camera_visible = pyqtSignal(bool)  # mostrar o amagar la càmera a la finestra
    confirmacio = pyqtSignal(str, str, object)   # (eina, detall, Future amb la resposta)
    notificacio = pyqtSignal(str)     # un avís de l'agenda (per a la notificació de Windows)
    eines_canviades = pyqtSignal()    # quan s'acaben de carregar els plugins i els servidors MCP

    def __init__(self, config):
        super().__init__()
        self.config = config
        self.loop = None              # el bucle d'asyncio (quan estigui en marxa)
        self.sessio = None            # la connexió amb Gemini (quan estigui connectat)
        self.silenciat = False        # el botó de silenciar el micròfon
        self.parlant = False          # si l'assistent està parlant ara mateix
        self.ultim_so = 0.0           # quan va sonar l'últim tros de veu
        self.descartar_audio = False  # per al botó d'interrompre
        self.mut_mobil = False        # l'ordre ve del mòbil: la resposta no sona per l'altaveu
        self.ha_saludat = False
        self.text_usuari = ""         # el que diu l'usuari, es va omplint a trossos
        self.text_ia = ""             # el que diu l'assistent, igual
        self.cua_altaveu = queue.Queue()
        self.avisos_pendents = []     # avisos que han arribat mentre no hi havia connexió
        self.client = None            # el client de Gemini (també per transcriure les confirmacions)

        # Confirmar per veu: la confirmació que espera resposta i la frase que s'està gravant
        self.confirmacio_pendent = None
        self.frase = []
        self.trossos_silenci = 0
        self.reconeixedor = ReconeixedorLocal()

        # Per detectar si l'usuari parla per sobre de l'assistent
        self.llindar = float(config.get("sensibilitat_interrupcio", 0.15))
        self.trossos_forts = 0
        self.trossos_previs = deque(maxlen=5)   # els últims trossos del micròfon

        self.camera = Camera()
        self.tasca_camera = None      # la tasca que envia imatges a Gemini

        # Plugins: els donem accés a la configuració, a la veu i al registre
        eines.context.config = config
        eines.context.avisar = self.avisar
        eines.context.missatge = self.missatge.emit
        eines.context.enviar_text = self.enviar_text
        self.missatge.connect(self._avisar_escoltadors)
        eines.carregar_plugins(config.get("plugins_desactivats", []))
        self._registrar_eines_camera()
        self.pont = PontMCP(self.missatge.emit)

    def _registrar_eines_camera(self):
        """Les eines de la càmera són aquí perquè necessiten la finestra i la connexió."""
        async def tancar():
            return self.tancar_camera()
        eines.registrar(eines.Eina(
            nom="obrir_camera", funcio=self._obrir_camera, asincrona=True, plugin="camera",
            descripcio="Obre la càmera web dins la finestra de l'assistent i et permet veure-hi. "
                       "Fes-la servir quan l'usuari et digui 'mostra'm el que veus', 'mira això', "
                       "'què tinc a la mà?' o semblant."))
        eines.registrar(eines.Eina(
            nom="tancar_camera", funcio=tancar, asincrona=True, plugin="camera",
            descripcio="Tanca la càmera web."))
        eines.PLUGINS["camera"] = "Càmera web"

    # ── Arrencar ─────────────────────────────────────────────────────────────

    def iniciar(self):
        """Engega l'altaveu, el micròfon i la connexió amb Gemini."""
        threading.Thread(target=self._fil_altaveu, daemon=True).start()

        try:
            self.micro = sd.RawInputStream(samplerate=RATE_MICRO, channels=1,
                                           dtype="int16", blocksize=1024,
                                           callback=self._quan_arriba_so)
            self.micro.start()
        except Exception as e:
            self.missatge.emit("err", f"No s'ha pogut obrir el micròfon: {e}")

        threading.Thread(target=self._fil_connexio, daemon=True).start()

    def _fil_connexio(self):
        asyncio.run(self._bucle_connexio())

    # ── Instruccions per a Gemini ────────────────────────────────────────────

    def _instruccions(self):
        nom = self.config["nom_assistent"]
        usuari = self.config["nom_usuari"]
        if usuari:
            com_dir_li = f"L'usuari es diu {usuari}; dirigeix-t'hi pel seu nom."
        else:
            com_dir_li = "Tracta l'usuari de 'senyor', amb respecte però amb confiança."
        ara = datetime.now()
        dies = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"]

        return (
            f"Ets {nom}, un assistent de veu personal inspirat en el JARVIS d'Iron Man, que viu "
            f"a l'ordinador de l'usuari (Windows) i el pot controlar amb les eines. "
            f"Parla de manera breu, clara i amable, com en una conversa. "
            f"Respon en l'idioma en què et parli l'usuari; si no està clar, en català. "
            f"{com_dir_li} "
            f"Quan et vas connectar era {dies[ara.weekday()]} {ara.strftime('%Y-%m-%d %H:%M')}; "
            f"si necessites l'hora exacta, fes servir data_i_hora. Les dates de les eines van "
            f"en format AAAA-MM-DDTHH:MM. "
            f"\n\nCOM TREBALLAR: "
            f"Quan l'usuari et demani fer alguna cosa, fes-la amb les eines, sense demanar "
            f"permís per a coses senzilles. Si cal, encadena diverses eines (per exemple, "
            f"buscar_fitxers i després llegir_fitxer; o activar_finestra i després escriure_text). "
            f"Si no saps què hi ha a la pantalla, fes servir mirar_pantalla. Fes servir "
            f"executar_powershell només si cap altra eina serveix. "
            f"No diguis mai que has fet una cosa si l'eina no t'ho ha confirmat. "
            f"Algunes eines són perilloses (esborrar, enviar correus o missatges, tancar "
            f"programes, apagar...): quan les facis servir, l'usuari haurà de confirmar-ho en "
            f"una finestra; si et torna que no ha donat permís, no ho tornis a provar. "
            f"\n\nAGENDA: Per a l'horari, les classes, els recordatoris i les tasques fes servir "
            f"l'agenda pròpia (afegir_esdeveniment, veure_agenda, afegir_recordatori, "
            f"afegir_tasca...). Si l'usuari parla de Google Calendar, Gmail, Drive o el seu correu, "
            f"fes servir les eines de Google. Quan et pregunti què té avui, mira l'agenda pròpia "
            f"i, si Google està connectat, també google_calendar_veure. "
            f"Si reps un missatge que comença per [AVÍS], és l'agenda (no l'usuari): digues-li "
            f"l'avís en veu alta, breument. "
            f"\n\nPer a preguntes d'actualitat (notícies, resultats), fes servir la cerca de Google. "
            f"És una conversa: si l'usuari et talla mentre parles, calla i escolta'l. "
            f"Si l'usuari et demana que miris alguna cosa o que li ensenyis què veus, obre la "
            f"càmera amb obrir_camera; a partir d'aquell moment rebràs imatges de la càmera. "
            f"Tanca-la amb tancar_camera quan l'usuari t'ho demani."
        )

    def _config_gemini(self):
        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=self._instruccions(),
            tools=[
                {"google_search": {}},                                  # cerca de Google integrada
                {"function_declarations": eines.declaracions()},        # plugins i servidors MCP
            ],
            speech_config={"voice_config": {"prebuilt_voice_config": {
                "voice_name": self.config["veu"]}}},
            input_audio_transcription={},    # que ens torni en text el que diu l'usuari
            output_audio_transcription={},   # i el que diu l'assistent
        )

    # ── Connexió amb Gemini ──────────────────────────────────────────────────

    async def _bucle_connexio(self):
        """Es connecta a Gemini i, si es talla la connexió, es torna a connectar."""
        self.loop = asyncio.get_running_loop()

        # Primer els servidors MCP, perquè les seves eines entrin a la llista
        await self.pont.iniciar()
        errors = [f"{n} ({d[7:]})" for n, d in eines.PLUGINS.items() if d.startswith("ERROR")]
        self.missatge.emit("sys", f"{len(eines.EINES)} eines a punt ({len(eines.PLUGINS)} plugins).")
        for e in errors:
            self.missatge.emit("err", f"El plugin {e} no s'ha pogut carregar.")
        self.eines_canviades.emit()

        client = self.client = genai.Client(api_key=self.config["api_key"])
        intent = 0

        while True:
            model = MODELS[intent % len(MODELS)]
            self.canvi_estat.emit("CONNECTANT")
            try:
                async with client.aio.live.connect(model=model, config=self._config_gemini()) as sessio:
                    self.sessio = sessio
                    self.missatge.emit("sys", f"Connectat a Gemini ({model}).")
                    self._posar_estat_normal()

                    if not self.ha_saludat:
                        self.ha_saludat = True
                        await sessio.send_realtime_input(text="Saluda breument l'usuari.")

                    # Si la càmera ja estava oberta d'abans de reconnectar
                    if self.camera.obert:
                        self._engegar_enviament_camera()
                    # Avisos de l'agenda que han arribat mentre no hi havia connexió
                    while self.avisos_pendents:
                        await self._dir_avis(self.avisos_pendents.pop(0))

                    await self._rebre(sessio)

            except Exception as e:
                self.sessio = None
                error = str(e)
                if "API key" in error:
                    self.missatge.emit("err", "La clau API de Gemini no és vàlida. "
                                              "Esborra-la de config.json i torna a obrir el programa.")
                    self.canvi_estat.emit("DESCONNECTAT")
                    return
                self.missatge.emit("err", f"S'ha perdut la connexió: {error[:150]}")
                self.canvi_estat.emit("DESCONNECTAT")
                intent += 1
                await asyncio.sleep(3)     # esperem una mica abans de tornar-ho a provar

    async def _rebre(self, sessio):
        """Llegeix tot el que ens envia Gemini: àudio, text i peticions d'eines."""
        while True:
            # receive() dona els missatges d'un torn de conversa i després s'acaba,
            # per això hi ha el "while True" a fora.
            missatges_rebuts = 0
            async for resposta in sessio.receive():
                missatges_rebuts += 1

                # 1. Àudio de la veu de l'assistent
                if resposta.data and not self.descartar_audio and not self.mut_mobil:
                    self.cua_altaveu.put(resposta.data)

                # 2. Textos (transcripcions) i finals de torn
                contingut = resposta.server_content
                if contingut:
                    if contingut.input_transcription and contingut.input_transcription.text:
                        self.text_usuari += contingut.input_transcription.text
                        self.descartar_audio = False   # l'usuari parla: torn nou
                    if contingut.output_transcription and contingut.output_transcription.text:
                        self._mostrar_text_usuari()
                        self.text_ia += contingut.output_transcription.text
                    if contingut.interrupted:
                        # Gemini ens avisa que l'usuari l'ha tallat: callem de seguida
                        self._buidar_altaveu()
                        self.descartar_audio = False
                        self.text_ia = ""
                        self.missatge.emit("sys", "M'has interromput.")
                    if contingut.turn_complete:
                        self._mostrar_text_usuari()
                        self._mostrar_text_ia()
                        self.descartar_audio = False
                        self.mut_mobil = False

                # 3. Gemini vol que executem una eina
                if resposta.tool_call:
                    await self._fer_eines(sessio, resposta.tool_call)

            if missatges_rebuts == 0:
                raise ConnectionError("Gemini ha tancat la connexió")

    # ── Eines ────────────────────────────────────────────────────────────────

    async def _fer_eines(self, sessio, peticio):
        """Executa les eines que demana Gemini i li torna els resultats."""
        self.canvi_estat.emit("PENSANT")
        respostes = []
        for crida in peticio.function_calls:
            arguments = dict(crida.args or {})
            resultat = await self._executar_eina(crida.name, arguments)
            if isinstance(resultat, eines.AmbImatge):
                # Primer li enviem la imatge, i després el text del resultat
                if resultat.jpeg:
                    await sessio.send_realtime_input(
                        video=types.Blob(data=resultat.jpeg, mime_type="image/jpeg"))
                resultat = resultat.text
            respostes.append(types.FunctionResponse(
                id=crida.id, name=crida.name, response={"result": str(resultat)}))
        await sessio.send_tool_response(function_responses=respostes)

    async def _executar_eina(self, nom, arguments):
        e = eines.EINES.get(nom)
        if e is None:
            return f"No existeix cap eina que es digui {nom}."
        self.missatge.emit("eina", f"Eina: {nom}")

        if self.config.get("confirmar_perilloses", True) and e.es_perillosa(arguments):
            detall = e.resum(arguments) if e.resum else json.dumps(arguments, ensure_ascii=False)
            if not await self._demanar_permis(nom, detall):
                self.missatge.emit("sys", f"No has donat permís per a {nom}.")
                return ("L'usuari ha dit que NO a la finestra de confirmació, així que no s'ha fet. "
                        "Digues-li directament (parlant-li a ell, en segona persona) que no ho has "
                        "fet, i no ho tornis a provar si no t'ho torna a demanar.")
            self.canvi_estat.emit("PENSANT")

        try:
            if e.asincrona:
                return await e.funcio(**arguments)
            # Les normals, en un altre fil: algunes tarden (buscar fitxers, Google...)
            return await asyncio.to_thread(eines.executar, nom, arguments)
        except Exception as err:
            return f"L'eina {nom} ha fallat: {err}"

    async def _demanar_permis(self, nom, detall):
        """Mostra la finestra de confirmació i espera que l'usuari respongui."""
        resposta = concurrent.futures.Future()
        if self.config.get("confirmar_per_veu", True):
            self.frase, self.trossos_silenci = [], 0
            self.confirmacio_pendent = resposta     # ara el micròfon escolta el sí o el no
            asyncio.get_running_loop().run_in_executor(None, self._preparar_reconeixedor)
        self.confirmacio.emit(nom, detall, resposta)
        for funcio in eines.context.en_confirmacio:      # per exemple, els botons de Telegram
            try:
                funcio(nom, detall, resposta)
            except Exception as e:
                print("[Confirmació]", e)
        try:
            return await asyncio.wait_for(asyncio.wrap_future(resposta), SEGONS_PER_CONFIRMAR)
        except asyncio.TimeoutError:
            return False
        finally:
            self.confirmacio_pendent = None

    def _preparar_reconeixedor(self):
        try:
            self.reconeixedor.preparar()
        except Exception as e:
            print("[Veu] El reconeixement de Windows no està disponible:", e)

    def _escoltar_confirmacio(self, dades, nivell):
        """Mentre hi ha una confirmació pendent, grava frase a frase el que diu l'usuari
        (en lloc d'enviar-ho a Gemini Live) i, quan acaba una frase, la fa transcriure."""
        parla = nivell > LLINDAR_VEU
        if not self.frase:
            if parla:
                self.frase = list(self.trossos_previs) + [dades]   # no perdem el principi
                self.trossos_silenci = 0
            else:
                self.trossos_previs.append(dades)
            return
        self.frase.append(dades)
        self.trossos_silenci = 0 if parla else self.trossos_silenci + 1
        if self.trossos_silenci >= TROSSOS_SILENCI_FINAL or len(self.frase) >= TROSSOS_MAXIMS_FRASE:
            audio = b"".join(self.frase)
            self.frase, self.trossos_silenci = [], 0
            self.trossos_previs.clear()
            asyncio.run_coroutine_threadsafe(self._decidir_per_veu(audio, self.confirmacio_pendent), self.loop)

    async def _decidir_per_veu(self, audio, resposta):
        if resposta is None or resposta.done():
            return
        wav = self._a_wav(audio)
        # 1. El reconeixement de Windows: ràpid i sense Internet
        text, segur = "", False
        ruta = Path(tempfile.gettempdir()) / f"jarvis_confirmacio_{time.time_ns()}.wav"
        try:
            ruta.write_bytes(wav)
            text, segur = await asyncio.wait_for(
                asyncio.to_thread(self.reconeixedor.reconeixer, ruta), 5)
        except Exception as e:
            self.reconeixedor.tancar()
            print("[Veu] Reconeixement local:", e)
        finally:
            ruta.unlink(missing_ok=True)
        decisio = interpretar_resposta(text) if text else None
        if decisio and not segur:
            decisio = None             # un sí només val si el reconeixedor n'està segur
        # 2. Si no ho ha entès clar, ho transcriu Gemini
        if decisio is None:
            text = await self._transcriure(wav) or text
            decisio = interpretar_resposta(text)
        if resposta is None or resposta.done() or not text:
            return                     # ja s'ha respost, o només era soroll
        self.missatge.emit("tu", text)
        if decisio is None:
            self.missatge.emit("sys", "No t'he entès: digues «sí» o «no», o fes servir la finestra.")
            return
        try:
            resposta.set_result(decisio)
        except concurrent.futures.InvalidStateError:
            return                     # ja s'havia respost a la finestra
        self.missatge.emit("sys", "Confirmat per veu." if decisio else "Denegat per veu.")

    @staticmethod
    def _a_wav(audio):
        """Posa la capçalera WAV a l'àudio del micròfon (16 kHz, mono, 16 bits)."""
        wav = io.BytesIO()
        with wave.open(wav, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE_MICRO)
            w.writeframes(audio)
        return wav.getvalue()

    async def _transcriure(self, wav):
        """Passa a text un WAV amb una crida a part a Gemini (com a molt uns segons)."""
        for model in MODELS_TRANSCRIPCIO:
            try:
                r = await asyncio.wait_for(self.client.aio.models.generate_content(model=model, contents=[
                    types.Part.from_bytes(data=wav, mime_type="audio/wav"),
                    "Transcriu exactament el que diu aquest àudio, en el seu idioma. Respon "
                    "només amb la transcripció; si no s'hi entén cap paraula, respon amb un buit."]),
                    SEGONS_TRANSCRIPCIO)
                return (r.text or "").strip()
            except Exception as e:
                print(f"[Veu] {model}: {str(e)[:120] or 'temps esgotat'}")
        return ""

    # ── Avisos de l'agenda ───────────────────────────────────────────────────

    def avisar(self, text):
        """La criden els plugins (des d'un altre fil) quan cal dir alguna cosa sense que
        l'usuari hagi preguntat res, per exemple un recordatori."""
        self.missatge.emit("avis", text)
        self.notificacio.emit(text)
        if self.sessio is not None and self.loop is not None:
            asyncio.run_coroutine_threadsafe(self._dir_avis(text), self.loop)
        else:
            self.avisos_pendents.append(text)

    async def _dir_avis(self, text):
        try:
            await self.sessio.send_realtime_input(
                text=f"[AVÍS] Digues-li això a l'usuari ara, amb naturalitat i sense dir la paraula "
                     f"'avís': {text}")
        except Exception:
            self.avisos_pendents.append(text)

    # ── Càmera ───────────────────────────────────────────────────────────────

    async def _obrir_camera(self):
        """Obre la càmera, la mostra a la finestra i comença a enviar-la a Gemini."""
        # Obrir la càmera tarda un o dos segons: ho fem en un altre fil
        ok = await asyncio.to_thread(self.camera.obrir)
        if not ok:
            return "No s'ha pogut obrir la càmera. Potser no n'hi ha cap o la fa servir un altre programa."

        self.camera_visible.emit(True)
        # Esperem la primera imatge (com a molt 3 segons) perquè Gemini la tingui
        # abans de respondre
        for _ in range(30):
            if self.camera.ultim_jpeg:
                break
            await asyncio.sleep(0.1)
        self._engegar_enviament_camera()
        return ("He obert la càmera dins la finestra de l'assistent. Ara reps una imatge "
                "de la càmera cada segon: descriu breument el que hi veus. Si la imatge és "
                "tota negra, digues que la càmera sembla tapada en lloc d'inventar-te-la.")

    def tancar_camera(self):
        self.camera.tancar()
        self.camera_visible.emit(False)
        return "He tancat la càmera."

    def canviar_camera(self):
        """Per al botó de la finestra: obre la càmera si està tancada, i al revés."""
        if self.camera.obert:
            self.tancar_camera()
        elif self.loop is not None:
            asyncio.run_coroutine_threadsafe(self._obrir_camera(), self.loop)
        else:
            self.missatge.emit("err", "Encara no estic connectat a Gemini.")

    def _engegar_enviament_camera(self):
        if self.tasca_camera is None or self.tasca_camera.done():
            self.tasca_camera = asyncio.create_task(self._enviar_camera())

    async def _enviar_camera(self):
        """Mentre la càmera estigui oberta, envia una imatge a Gemini cada segon."""
        while self.camera.obert and self.sessio is not None:
            if self.camera.ultim_jpeg:
                imatge = types.Blob(data=self.camera.ultim_jpeg, mime_type="image/jpeg")
                try:
                    await self.sessio.send_realtime_input(video=imatge)
                except Exception:
                    return            # s'ha tallat la connexió; es tornarà a engegar en reconnectar
            await asyncio.sleep(SEGONS_ENTRE_IMATGES)

    def _mostrar_text_usuari(self):
        if self.text_usuari.strip():
            self.missatge.emit("tu", self.text_usuari.strip())
        self.text_usuari = ""

    def _mostrar_text_ia(self):
        if self.text_ia.strip():
            self.missatge.emit("ia", self.text_ia.strip())
        self.text_ia = ""

    # ── Micròfon ─────────────────────────────────────────────────────────────

    def _quan_arriba_so(self, dades, frames, temps, estat):
        """La crida sounddevice cada vegada que té un tros d'àudio del micròfon."""
        if self.sessio is None or self.loop is None or self.silenciat:
            return

        dades = bytes(dades)
        nivell = calcular_nivell(dades)
        assistent_sona = self.parlant or time.time() - self.ultim_so < MARGE_ECO

        if self.confirmacio_pendent is not None:
            # Hi ha una acció esperant permís: el que digui l'usuari és la resposta
            # (sí o no) i no va a Gemini. Si l'assistent encara sona, és el seu eco.
            if not assistent_sona:
                self.nivell.emit(nivell)
                self._escoltar_confirmacio(dades, nivell)
            return

        if assistent_sona:
            # L'assistent està parlant. El micròfon sent la seva veu per l'altaveu
            # (l'eco), i si l'enviéssim tot, s'interrompria a si mateix.
            # Per això només enviem quan el so és més fort que l'eco durant uns
            # quants trossos seguits: vol dir que l'usuari li parla per sobre.
            self.trossos_previs.append(dades)
            if nivell > self.llindar:
                self.trossos_forts += 1
            else:
                self.trossos_forts = 0
            if self.trossos_forts < TROSSOS_PER_INTERROMPRE:
                return
            # Enviem també els trossos d'abans, perquè no es perdi el principi
            # del que diu l'usuari. Gemini ho sentirà i deixarà de parlar.
            per_enviar = list(self.trossos_previs)
            self.trossos_previs.clear()
        else:
            self.trossos_forts = 0
            self.nivell.emit(nivell)
            per_enviar = [dades]

        for tros in per_enviar:
            blob = types.Blob(data=tros, mime_type=f"audio/pcm;rate={RATE_MICRO}")
            # Aquesta funció no és asíncrona, així que li demanem al bucle
            # d'asyncio que faci l'enviament per nosaltres
            asyncio.run_coroutine_threadsafe(self.sessio.send_realtime_input(audio=blob), self.loop)

    # ── Altaveu ──────────────────────────────────────────────────────────────

    def _fil_altaveu(self):
        """Fil que reprodueix l'àudio de la cua. Funciona tota l'estona."""
        try:
            altaveu = sd.RawOutputStream(samplerate=RATE_ALTAVEU, channels=1, dtype="int16")
            altaveu.start()
        except Exception as e:
            self.missatge.emit("err", f"No s'ha pogut obrir l'altaveu: {e}")
            return

        while True:
            try:
                dades = self.cua_altaveu.get(timeout=0.3)
            except queue.Empty:
                # No ha arribat àudio en una estona: l'assistent ja ha acabat de parlar
                if self.parlant:
                    self.parlant = False
                    self.nivell.emit(0.0)
                    self._posar_estat_normal()
                continue

            if not self.parlant:
                self.parlant = True
                self.canvi_estat.emit("PARLANT")
            self.ultim_so = time.time()
            self.nivell.emit(calcular_nivell(dades))
            try:
                altaveu.write(dades)
            except Exception:
                return                 # el programa s'està tancant

    def _buidar_altaveu(self):
        """Llença l'àudio que encara no s'ha reproduït."""
        while not self.cua_altaveu.empty():
            try:
                self.cua_altaveu.get_nowait()
            except queue.Empty:
                break
        self.ultim_so = 0.0           # així el micròfon torna a escoltar de seguida

    # ── Coses que fa la finestra ─────────────────────────────────────────────

    def enviar_text(self, text, des_del_mobil=False):
        """Envia a Gemini el que l'usuari ha escrit (a la finestra o des del mòbil).
        Torna False si encara no hi ha connexió."""
        if self.sessio is None or self.loop is None:
            self.missatge.emit("err", "Encara no estic connectat a Gemini.")
            return False
        self.missatge.emit("tu", ("📱 " if des_del_mobil else "") + text)
        self.descartar_audio = False
        self.canvi_estat.emit("PENSANT")
        if des_del_mobil:
            # L'usuari no és davant de l'ordinador: la resposta li arriba escrita al mòbil
            self.mut_mobil = True
            text = f"(Missatge escrit des del mòbil; l'usuari no és davant de l'ordinador.) {text}"
        asyncio.run_coroutine_threadsafe(self.sessio.send_realtime_input(text=text), self.loop)
        return True

    def _avisar_escoltadors(self, tipus, text):
        """Passa cada missatge del registre als plugins que l'escolten (Telegram...)."""
        for funcio in eines.context.escoltadors:
            try:
                funcio(tipus, text)
            except Exception as e:
                print("[Escoltador]", e)

    def canviar_silenci(self):
        """Activa o desactiva el micròfon. Torna True si ara està silenciat."""
        self.silenciat = not self.silenciat
        self._posar_estat_normal()
        return self.silenciat

    def interrompre(self):
        """Fa callar l'assistent: llença la resta de la resposta."""
        # Només descartem el que arribi si la resposta encara no ha acabat
        # (si no, ens menjaríem el principi de la resposta següent)
        self.descartar_audio = bool(self.text_ia)
        self._buidar_altaveu()

    def _posar_estat_normal(self):
        if self.sessio is None:
            return
        self.canvi_estat.emit("SILENCIAT" if self.silenciat else "ESCOLTANT")
