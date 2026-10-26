# plugins/ordinador.py
# Controlar Windows: finestres, programes, teclat, pantalla, porta-retalls,
# multimèdia, apagar i, com a últim recurs, ordres de PowerShell.

import io
import os
import subprocess
import time

import psutil

from eines import AmbImatge, eina, enter, opcions, text
from plugins.basiques import premer_tecla

DESCRIPCIO = "Finestres, teclat, pantalla, porta-retalls, multimèdia i PowerShell"


# ─────────────────────────────────────────────────────────────────────────────
#  Veure la pantalla
# ─────────────────────────────────────────────────────────────────────────────

@eina("Fa una captura de la pantalla i te l'envia perquè la puguis veure. Fes-la servir "
      "quan l'usuari digui 'mira la meva pantalla', 'què veus a la pantalla?', 'llegeix "
      "això', o quan necessitis veure què hi ha obert abans de fer alguna cosa.")
def mirar_pantalla():
    from PIL import ImageGrab
    imatge = ImageGrab.grab(all_screens=False)
    imatge.thumbnail((1280, 1280))
    dades = io.BytesIO()
    imatge.convert("RGB").save(dades, "JPEG", quality=70)
    return AmbImatge("T'he enviat una captura de la pantalla. Descriu o fes servir el que hi veus.",
                     dades.getvalue())


@eina("Desa una captura de la pantalla com a imatge a la carpeta Imatges.")
def desar_captura():
    from PIL import ImageGrab
    from plugins.fitxers import ruta
    carpeta = ruta("Imatges") / "Captures JARVIS"
    carpeta.mkdir(parents=True, exist_ok=True)
    fitxer = carpeta / time.strftime("captura_%Y-%m-%d_%H-%M-%S.png")
    ImageGrab.grab().save(fitxer)
    return f"Captura desada a {fitxer}."


# ─────────────────────────────────────────────────────────────────────────────
#  Finestres i programes
# ─────────────────────────────────────────────────────────────────────────────

@eina("Llista les finestres obertes.")
def llistar_finestres():
    import pygetwindow as gw
    titols = [t for t in gw.getAllTitles() if t.strip()]
    return "Finestres obertes:\n" + "\n".join(dict.fromkeys(titols)) if titols else "No hi ha finestres obertes."


def _finestra(nom):
    import pygetwindow as gw
    nom = nom.lower()
    for f in gw.getAllWindows():
        if f.title and nom in f.title.lower():
            return f
    return None


@eina("Porta una finestra al davant (per exemple 'Chrome', 'Word', 'WhatsApp').",
      parametres={"nom": text("Part del títol de la finestra")})
def activar_finestra(nom):
    f = _finestra(nom)
    if f is None:
        return f"No he trobat cap finestra que contingui «{nom}»."
    try:
        if f.isMinimized:
            f.restore()
        f.activate()
    except Exception:
        # Windows de vegades no deixa canviar el focus; ho provem amb Alt
        import pyautogui
        pyautogui.press("alt")
        f.activate()
    return f"He portat al davant «{f.title}»."


@eina("Minimitza, maximitza o restaura una finestra, o mostra l'escriptori (nom='escriptori').",
      parametres={"nom": text("Part del títol de la finestra, o 'escriptori'"),
                  "accio": opcions("Què fer", ["minimitzar", "maximitzar", "restaurar"])})
def finestra(nom, accio):
    if nom.lower() in ("escriptori", "desktop"):
        import pyautogui
        pyautogui.hotkey("win", "d")
        return "He mostrat l'escriptori."
    f = _finestra(nom)
    if f is None:
        return f"No he trobat cap finestra que contingui «{nom}»."
    {"minimitzar": f.minimize, "maximitzar": f.maximize, "restaurar": f.restore}[accio]()
    return f"Fet: {accio} «{f.title}»."


@eina("Tanca un programa (per exemple 'chrome', 'spotify', 'word'). Els canvis que no "
      "s'hagin desat es poden perdre.",
      parametres={"nom": text("Nom del programa")},
      perillosa=True, resum=lambda a: f"Tancar el programa «{a.get('nom', '')}»")
def tancar_programa(nom):
    equivalents = {"word": "winword", "excel": "excel", "powerpoint": "powerpnt",
                   "chrome": "chrome", "edge": "msedge", "bloc de notes": "notepad"}
    cerca = equivalents.get(nom.lower(), nom.lower()).replace(".exe", "")
    tancats = 0
    for p in psutil.process_iter(["name"]):
        if p.info["name"] and p.info["name"].lower().replace(".exe", "") == cerca:
            try:
                p.terminate()
                tancats += 1
            except Exception:
                pass
    return f"He tancat {nom}." if tancats else f"No he trobat {nom} obert."


# ─────────────────────────────────────────────────────────────────────────────
#  Teclat i porta-retalls
# ─────────────────────────────────────────────────────────────────────────────

@eina("Escriu un text a la finestra que estigui activa, com si l'usuari el teclegés. "
      "Abans, porta al davant la finestra on s'ha d'escriure amb activar_finestra.",
      parametres={"text": text("El text que s'ha d'escriure")})
def escriure_text(text):
    import pyperclip
    import pyautogui
    # Enganxar és més ràpid i respecta els accents (pyautogui.write no els fa bé)
    anterior = pyperclip.paste()
    pyperclip.copy(text)
    time.sleep(0.1)
    pyautogui.hotkey("ctrl", "v")
    time.sleep(0.2)
    pyperclip.copy(anterior)
    return "Text escrit."


@eina("Prem una tecla o una combinació de tecles a la finestra activa, per exemple "
      "'enter', 'ctrl+s', 'alt+tab', 'ctrl+shift+t', 'f5', 'espai'.",
      parametres={"tecles": text("Les tecles, separades per +")},
      perillosa=True, resum=lambda a: f"Prémer les tecles {a.get('tecles', '')}")
def premer_tecles(tecles):
    import pyautogui
    noms = {"espai": "space", "intro": "enter", "retorn": "enter", "suprimir": "delete",
            "esborrar": "backspace", "majúscules": "shift", "control": "ctrl", "windows": "win"}
    parts = [noms.get(t.strip().lower(), t.strip().lower()) for t in tecles.split("+")]
    pyautogui.hotkey(*parts)
    return f"He premut {tecles}."


@eina("Llegeix el text que hi ha copiat al porta-retalls.")
def llegir_portaretalls():
    import pyperclip
    contingut = pyperclip.paste()
    return contingut[:8000] if contingut else "El porta-retalls és buit."


@eina("Copia un text al porta-retalls perquè l'usuari el pugui enganxar.",
      parametres={"text": text("El text que s'ha de copiar")})
def copiar_al_portaretalls(text):
    import pyperclip
    pyperclip.copy(text)
    return "Copiat al porta-retalls."


# ─────────────────────────────────────────────────────────────────────────────
#  Música i vídeo (funciona amb Spotify, YouTube, el reproductor de Windows...)
# ─────────────────────────────────────────────────────────────────────────────

TECLES_MULTIMEDIA = {"play_pausa": 0xB3, "seguent": 0xB0, "anterior": 0xB1, "aturar": 0xB2}


@eina("Controla la música o el vídeo que s'està reproduint (Spotify, YouTube...): "
      "posar en marxa o en pausa, cançó següent o anterior.",
      parametres={"accio": opcions("Què fer", list(TECLES_MULTIMEDIA))})
def control_multimedia(accio):
    premer_tecla(TECLES_MULTIMEDIA[accio])
    return f"Fet ({accio})."


# ─────────────────────────────────────────────────────────────────────────────
#  Configuració de Windows i energia
# ─────────────────────────────────────────────────────────────────────────────

PAGINES = {
    "wifi": "ms-settings:network-wifi", "bluetooth": "ms-settings:bluetooth",
    "pantalla": "ms-settings:display", "so": "ms-settings:sound",
    "bateria": "ms-settings:batterysaver", "actualitzacions": "ms-settings:windowsupdate",
    "aplicacions": "ms-settings:appsfeatures", "fons": "ms-settings:personalization-background",
    "notificacions": "ms-settings:notifications", "emmagatzematge": "ms-settings:storagesense",
    "impressores": "ms-settings:printers", "idioma": "ms-settings:regionlanguage",
    "privadesa": "ms-settings:privacy", "càmera": "ms-settings:privacy-webcam",
    "micròfon": "ms-settings:privacy-microphone",
}


@eina("Obre una pàgina de la Configuració de Windows (wifi, bluetooth, pantalla, so, bateria, "
      "actualitzacions, aplicacions, fons, notificacions, emmagatzematge, impressores, "
      "idioma, privadesa, càmera, micròfon).",
      parametres={"pagina": opcions("Quina pàgina", list(PAGINES))})
def obrir_configuracio(pagina):
    os.startfile(PAGINES.get(pagina, "ms-settings:"))
    return f"He obert la configuració de {pagina}."


@eina("Bloqueja l'ordinador (cal la contrasenya o el PIN per tornar-hi).")
def bloquejar_ordinador():
    import ctypes
    ctypes.windll.user32.LockWorkStation()
    return "Ordinador bloquejat."


@eina("Apaga, reinicia o posa en repòs l'ordinador, ara o d'aquí uns minuts. "
      "També pot cancel·lar un apagat programat.",
      parametres={"accio": opcions("Què fer", ["apagar", "reiniciar", "repos", "cancel·lar"]),
                  "minuts": enter("D'aquí a quants minuts (per defecte 0, ara)")},
      requerits=["accio"],
      perillosa=lambda a: a.get("accio") != "cancel·lar",
      resum=lambda a: f"{a.get('accio', '').capitalize()} l'ordinador"
                      + (f" d'aquí {a['minuts']} minuts" if a.get("minuts") else " ara"))
def energia(accio, minuts=0):
    segons = max(0, int(minuts) * 60)
    if accio == "cancel·lar":
        subprocess.run(["shutdown", "/a"], capture_output=True)
        return "He cancel·lat l'apagat programat."
    if accio == "repos":
        subprocess.Popen(["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"])
        return "Posant l'ordinador en repòs."
    opcio = "/s" if accio == "apagar" else "/r"
    subprocess.run(["shutdown", opcio, "/t", str(segons)], capture_output=True)
    return f"L'ordinador es farà {accio} d'aquí {minuts} minuts." if minuts else f"Fent {accio}."


# ─────────────────────────────────────────────────────────────────────────────
#  PowerShell: per a tot el que no tingui una eina pròpia
# ─────────────────────────────────────────────────────────────────────────────

@eina("Executa una ordre de PowerShell a l'ordinador i torna el que surt. Fes-la servir "
      "NOMÉS quan cap altra eina serveixi (per exemple: saber la IP, la versió de Windows, "
      "els programes instal·lats, canviar una opció del sistema...). Explica abans a "
      "l'usuari què farà l'ordre.",
      parametres={"ordre": text("L'ordre de PowerShell"),
                  "explicacio": text("Què fa l'ordre, en una frase per a l'usuari")},
      requerits=["ordre", "explicacio"],
      perillosa=True,
      resum=lambda a: f"{a.get('explicacio', '')}\n\nOrdre: {a.get('ordre', '')}")
def executar_powershell(ordre, explicacio=""):
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", ordre],
                           capture_output=True, text=True, timeout=60,
                           encoding="utf-8", errors="replace",
                           creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        return "L'ordre ha tardat més d'un minut i l'he aturada."
    sortida = (r.stdout or "") + (("\nErrors:\n" + r.stderr) if r.stderr.strip() else "")
    sortida = sortida.strip() or "L'ordre s'ha executat i no ha tornat cap text."
    return sortida[:6000]
