# plugins/telegram.py
# Donar ordres a JARVIS des del mòbil, amb un bot de Telegram.
#
# Com es posa en marxa (una sola vegada, ho explica el README):
#   1. A Telegram, parla amb @BotFather, escriu /newbot i segueix els passos.
#      Et dona un "token", que és com la contrasenya del bot.
#   2. Posa'l a config.json:  "telegram_token": "123456789:AA..."
#   3. Obre JARVIS: al registre surt un codi. Envia'l al teu bot ("/vincular 123456").
#      A partir d'aquí el bot només obeeix el teu compte de Telegram.
#
# Com funciona: un fil pregunta a Telegram si hi ha missatges nous ("long
# polling"), així no cal obrir cap port de l'ordinador. Quan n'hi ha un del
# propietari, l'envia a Gemini com si l'haguessis escrit a la finestra, i la
# resposta te la torna escrita al xat. Les accions perilloses també es poden
# confirmar al mòbil amb dos botons.

import queue
import secrets
import threading
import time

import requests

from config import desar_config
from eines import eina, text

DESCRIPCIO = "Ordres des del mòbil amb un bot de Telegram"

API = "https://api.telegram.org/bot{token}/{metode}"
SEGONS_MODE_MOBIL = 300      # durant aquest temps després d'un missatge del mòbil, les respostes hi van
INTENTS_PER_VINCULAR = 5     # després de tants codis equivocats, no es pot vincular fins a reiniciar
SEGONS_REINTENT = 15         # si no hi ha connexió amb Telegram en arrencar, cada quant ho tornem a provar

AJUDA = ("Sóc JARVIS. Escriu-me el que vulguis que faci a l'ordinador, com si m'ho diguessis "
         "de paraula: «Què tinc avui?», «Posa música lofi», «Quant ocupa la carpeta Baixades?»...\n\n"
         "Si una acció és perillosa (esborrar, enviar, apagar...), et preguntaré aquí amb dos botons.")

_bot = None


class TokenInvalid(Exception):
    pass


class BotTelegram:
    def __init__(self, context):
        self.context = context
        self.config = context.config
        self.token = self.config["telegram_token"].strip()
        self.usuari = self.config.get("telegram_usuari")      # l'id de Telegram del propietari
        self.codi = f"{secrets.randbelow(10 ** 6):06d}"
        self.intents_fallits = 0
        self.ultim_mobil = 0.0          # quan va arribar l'últim missatge del mòbil
        self.confirmacions = {}         # id curt → Future de la confirmació
        self.cua = queue.Queue()        # el que s'ha d'enviar a Telegram

    # ── Parlar amb l'API de Telegram ────────────────────────────────────────

    def _api(self, metode, temps=15, **parametres):
        r = requests.post(API.format(token=self.token, metode=metode), json=parametres, timeout=temps)
        if r.status_code in (401, 404):
            raise TokenInvalid()        # Telegram no coneix aquest token (o s'ha revocat)
        dades = r.json()
        if not dades.get("ok"):
            raise RuntimeError(f"{r.status_code} {dades.get('description', '')}")
        return dades["result"]

    def enviar(self, text_, **altres):
        """Posa un missatge a la cua per al propietari (l'envia el fil d'enviament)."""
        if self.usuari:
            self.cua.put(("sendMessage", {"chat_id": self.usuari, "text": text_[:4000], **altres}, None))

    def _fil_enviament(self):
        while True:
            metode, parametres, en_acabar = self.cua.get()
            try:
                resultat = self._api(metode, **parametres)
                if en_acabar:
                    en_acabar(resultat)
            except Exception as e:
                print("[Telegram] No s'ha pogut enviar:", e)

    # ── Rebre missatges ─────────────────────────────────────────────────────

    def _fil_escolta(self):
        time.sleep(3)                   # que la finestra ja estigui a punt per mostrar els avisos
        avisat = False
        while True:
            try:
                nom_bot = self._api("getMe")["username"]
                # Ignorem els missatges que es van enviar mentre JARVIS estava tancat:
                # una ordre vella ("apaga l'ordinador") no s'ha d'executar hores després.
                vells = self._api("getUpdates", offset=-1, timeout=0)
                desplacament = vells[-1]["update_id"] + 1 if vells else None
                break
            except TokenInvalid:
                self.context.missatge("err", "El token de Telegram no és vàlid. Revisa telegram_token a config.json.")
                return
            except Exception as e:
                # Sense Internet, o la xarxa ha tallat la connexió: ho tornem a provar
                if not avisat:
                    self.context.missatge("sys", f"Telegram: encara no hi ha connexió ({str(e)[:80]}). "
                                                 f"Ho torno a provar cada {SEGONS_REINTENT} segons.")
                    avisat = True
                time.sleep(SEGONS_REINTENT)
        if self.usuari:
            self.context.missatge("sys", f"Telegram connectat: escriu a @{nom_bot} des del mòbil.")
        else:
            self.context.missatge("sys", f"Telegram: per vincular el teu mòbil, envia a @{nom_bot} "
                                         f"el missatge  /vincular {self.codi}")
        while True:
            try:
                parametres = {"timeout": 30, "allowed_updates": ["message", "callback_query"]}
                if desplacament:
                    parametres["offset"] = desplacament
                for u in self._api("getUpdates", temps=40, **parametres):
                    desplacament = u["update_id"] + 1
                    try:
                        if "message" in u:
                            self._missatge(u["message"])
                        elif "callback_query" in u:
                            self._boto(u["callback_query"])
                    except Exception as e:
                        print("[Telegram]", e)
            except TokenInvalid:
                self.context.missatge("err", "Telegram ha deixat d'acceptar el token (potser l'has revocat). "
                                             "Posa el nou a config.json i torna a obrir JARVIS.")
                return
            except Exception as e:
                print("[Telegram] Sense connexió:", e)
                time.sleep(5)

    def _missatge(self, m):
        if m["chat"]["type"] != "private":
            return
        de_qui = m["from"]["id"]
        text_ = (m.get("text") or "").strip()

        if not self.usuari:
            self._vincular(de_qui, m["chat"]["id"], text_)
            return
        if de_qui != self.usuari:
            self.context.missatge("sys", "Telegram: he ignorat un missatge d'algú que no és el propietari.")
            return

        if text_ in ("/start", "/ajuda", "/help"):
            self.enviar(AJUDA)
        elif not text_:
            self.enviar("De moment només entenc missatges de text.")
        else:
            self.ultim_mobil = time.time()
            if self.context.enviar_text(text_, des_del_mobil=True) is False:
                self.enviar("Encara no estic connectat a Gemini. Torna-ho a provar d'aquí una estona.")
            else:
                self.cua.put(("sendChatAction", {"chat_id": self.usuari, "action": "typing"}, None))

    def _vincular(self, de_qui, xat, text_):
        respondre = lambda t: self.cua.put(("sendMessage", {"chat_id": xat, "text": t}, None))
        if self.intents_fallits >= INTENTS_PER_VINCULAR:
            return
        if text_.replace("/vincular", "").strip() == self.codi:
            self.usuari = de_qui
            self.config["telegram_usuari"] = de_qui
            desar_config(self.config)
            self.context.missatge("sys", "Telegram: mòbil vinculat. Ara el bot només t'obeeix a tu.")
            respondre("Fet! Ara aquest bot només t'obeeix a tu.\n\n" + AJUDA)
        elif text_.startswith("/vincular"):
            self.intents_fallits += 1
            respondre("Aquest codi no és correcte.")
            if self.intents_fallits >= INTENTS_PER_VINCULAR:
                self.context.missatge("err", "Telegram: massa codis equivocats. No es podrà vincular "
                                             "cap mòbil fins que tornis a obrir JARVIS.")
        else:
            respondre("Aquest bot és privat. Si n'ets el propietari, envia /vincular i el codi que surt a JARVIS.")

    def _boto(self, b):
        if b["from"]["id"] != self.usuari:
            return
        resposta, _, id_ = b.get("data", "").partition(":")
        futur = self.confirmacions.pop(id_, None)
        missatge = "Aquesta pregunta ja s'havia respost."
        if futur is not None and not futur.done():
            try:
                futur.set_result(resposta == "si")
                missatge = "D'acord, ho faig." if resposta == "si" else "D'acord, no ho faig."
            except Exception:
                pass
        self.cua.put(("answerCallbackQuery", {"callback_query_id": b["id"], "text": missatge}, None))

    # ── El que arriba de l'assistent ────────────────────────────────────────

    def mode_mobil(self):
        return time.time() - self.ultim_mobil < SEGONS_MODE_MOBIL

    def escoltar(self, tipus, text_):
        """Rep tots els missatges del registre i passa al mòbil els que toca."""
        if tipus == "avis" and self.config.get("telegram_avisos", True):
            self.enviar("🔔 " + text_)           # els recordatoris arriben sempre al mòbil
        elif tipus == "ia" and self.mode_mobil():
            self.enviar(text_)
        elif tipus == "err" and self.mode_mobil():
            self.enviar("⚠️ " + text_)

    def demanar_permis(self, nom, detall, futur):
        """Si l'usuari parla des del mòbil, la confirmació li arriba amb dos botons."""
        if not self.usuari or not self.mode_mobil():
            return
        id_ = secrets.token_hex(4)
        self.confirmacions[id_] = futur
        botons = {"inline_keyboard": [[{"text": "✅ Sí, fes-ho", "callback_data": f"si:{id_}"},
                                       {"text": "❌ No", "callback_data": f"no:{id_}"}]]}
        pregunta = f"⚠️ Permets que faci això?\n\n{detall}\n\n(eina: {nom})"

        def quan_enviat(missatge):
            # Quan es respongui (aquí, a la finestra, per veu o perquè passa el temps),
            # canviem el missatge perquè no quedin botons que ja no serveixen.
            def quan_respost(f):
                self.confirmacions.pop(id_, None)
                if f.cancelled():
                    final = "⌛ No has respost a temps: no ho he fet."
                else:
                    final = "✅ Permís donat." if f.result() else "❌ No ho he fet."
                self.cua.put(("editMessageText", {"chat_id": self.usuari, "message_id": missatge["message_id"],
                                                  "text": f"{pregunta}\n\n{final}"}, None))
            futur.add_done_callback(quan_respost)

        self.cua.put(("sendMessage", {"chat_id": self.usuari, "text": pregunta[:4000],
                                      "reply_markup": botons}, quan_enviat))

    def engegar(self):
        threading.Thread(target=self._fil_enviament, daemon=True).start()
        threading.Thread(target=self._fil_escolta, daemon=True).start()
        self.context.escoltadors.append(self.escoltar)
        self.context.en_confirmacio.append(self.demanar_permis)


@eina("Envia un missatge al mòbil de l'usuari per Telegram (per exemple una llista, un "
      "enllaç o un recordatori que vulgui tenir a mà).",
      parametres={"missatge": text("El text que s'ha d'enviar")})
def enviar_al_mobil(missatge):
    if _bot is None or not _bot.usuari:
        return "Telegram no està configurat. S'explica al README (secció Telegram)."
    _bot.enviar(missatge)
    return "Enviat al mòbil."


def iniciar(context):
    global _bot
    if not context.config.get("telegram_token", "").strip():
        return                          # sense token, el plugin no fa res
    _bot = BotTelegram(context)
    _bot.engegar()
