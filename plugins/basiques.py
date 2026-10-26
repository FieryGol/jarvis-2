# plugins/basiques.py
# Les eines de la primera versió: aplicacions, web, volum, sistema, data i notes.

import ctypes
import os
import platform
import time
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus

import psutil

from config import CARPETA
from eines import eina, enter, opcions, text

DESCRIPCIO = "Aplicacions, web, volum, estat del sistema, data i notes"

FITXER_NOTES = CARPETA / "notes.txt"
ES_WINDOWS = platform.system() == "Windows"

# Noms que la gent diu → el que Windows sap obrir.
# Les que acaben amb ":" són enllaços d'aplicacions de la Microsoft Store o de Windows.
APLICACIONS = {
    "bloc de notes": "notepad",
    "notepad": "notepad",
    "calculadora": "calc",
    "explorador": "explorer",
    "explorador de fitxers": "explorer",
    "paint": "mspaint",
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "msedge",
    "word": "winword",
    "excel": "excel",
    "powerpoint": "powerpnt",
    "spotify": "spotify:",
    "whatsapp": "whatsapp:",
    "configuració": "ms-settings:",
    "configuracio": "ms-settings:",
    "terminal": "wt",
    "càmera": "microsoft.windows.camera:",
    "rellotge": "ms-clock:",
    "calendari": "outlookcal:",
    "correu": "outlookmail:",
    "botiga": "ms-windows-store:",
    "visual studio code": "code",
    "vs code": "code",
}


@eina("Obre una aplicació de l'ordinador, per exemple la calculadora, el bloc de notes, "
      "Chrome, Word, Spotify o WhatsApp.",
      parametres={"nom": text("Nom de l'aplicació")})
def obrir_aplicacio(nom):
    if not ES_WINDOWS:
        return "Aquesta eina només funciona a Windows."
    nom_net = nom.strip().lower()
    ordre = APLICACIONS.get(nom_net, nom_net)   # si no és a la llista, ho provem tal qual
    try:
        os.startfile(ordre)
        return f"He obert {nom}."
    except Exception:
        return (f"No he trobat cap aplicació que es digui '{nom}'. Si està instal·lada, "
                f"prova amb el nom exacte o cerca-la amb buscar_fitxers.")


@eina("Obre una pàgina web al navegador, o fa una cerca a Google al navegador "
      "si l'usuari vol veure-ho a la pantalla.",
      parametres={"text": text("Una adreça web (youtube.com) o el que s'ha de cercar")})
def obrir_web(text):
    text = text.strip()
    sembla_adreca = "." in text and " " not in text
    if sembla_adreca:
        if not text.startswith("http"):
            text = "https://" + text
        webbrowser.open(text)
        return f"He obert {text} al navegador."
    webbrowser.open("https://www.google.com/search?q=" + quote_plus(text))
    return f"He cercat '{text}' a Google al navegador."


# Codis de les tecles multimèdia de volum a Windows
TECLA_SILENCI = 0xAD
TECLA_BAIXAR = 0xAE
TECLA_PUJAR = 0xAF


def premer_tecla(codi):
    """Simula que es prem i es deixa anar una tecla."""
    ctypes.windll.user32.keybd_event(codi, 0, 0, 0)   # prémer
    ctypes.windll.user32.keybd_event(codi, 0, 2, 0)   # deixar anar


@eina("Puja, baixa o silencia el volum de l'ordinador.",
      parametres={"accio": opcions("Què s'ha de fer", ["pujar", "baixar", "silenciar"]),
                  "quantitat": enter("Quant s'ha de pujar o baixar, en percentatge (per defecte 10)")})
def control_volum(accio, quantitat=10):
    if not ES_WINDOWS:
        return "Aquesta eina només funciona a Windows."
    accio = accio.lower()
    vegades = max(1, int(quantitat) // 2)    # cada tecla de volum mou un 2%
    if accio == "pujar":
        for _ in range(vegades):
            premer_tecla(TECLA_PUJAR)
            time.sleep(0.01)
        return f"He pujat el volum un {vegades * 2}% aproximadament."
    if accio == "baixar":
        for _ in range(vegades):
            premer_tecla(TECLA_BAIXAR)
            time.sleep(0.01)
        return f"He baixat el volum un {vegades * 2}% aproximadament."
    if accio == "silenciar":
        premer_tecla(TECLA_SILENCI)
        return "He activat o desactivat el silenci."
    return "No entenc l'acció. Ha de ser pujar, baixar o silenciar."


@eina("Diu com va l'ordinador: ús de CPU, memòria, disc, bateria i els programes que "
      "gasten més memòria.")
def estat_del_sistema():
    cpu = psutil.cpu_percent(interval=0.5)
    memoria = psutil.virtual_memory()
    disc = psutil.disk_usage("C:\\" if ES_WINDOWS else "/")
    text = (f"CPU: {cpu:.0f}%. "
            f"Memòria: {memoria.percent:.0f}% "
            f"({memoria.used / 1024**3:.1f} de {memoria.total / 1024**3:.1f} GB). "
            f"Disc: {disc.percent:.0f}% ple ({disc.free / 1024**3:.0f} GB lliures).")
    bateria = psutil.sensors_battery()
    if bateria is not None:
        endoll = "endollat" if bateria.power_plugged else "sense endollar"
        text += f" Bateria: {bateria.percent:.0f}% ({endoll})."

    # Els 5 programes que gasten més memòria (sumant les finestres de cada un)
    per_programa = {}
    for p in psutil.process_iter(["name", "memory_info"]):
        try:
            nom = p.info["name"] or "?"
            per_programa[nom] = per_programa.get(nom, 0) + p.info["memory_info"].rss
        except Exception:
            pass
    primers = sorted(per_programa.items(), key=lambda x: -x[1])[:5]
    text += " Programes que gasten més memòria: " + ", ".join(
        f"{nom} ({mem / 1024**2:.0f} MB)" for nom, mem in primers) + "."
    return text


DIES = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"]
MESOS = ["gener", "febrer", "març", "abril", "maig", "juny", "juliol",
         "agost", "setembre", "octubre", "novembre", "desembre"]


def data_en_catala(moment):
    dia = DIES[moment.weekday()]
    mes = MESOS[moment.month - 1]
    # En català és "d'abril", "d'agost", "d'octubre", però "de maig"
    de_mes = f"d'{mes}" if mes[0] in "aeiou" else f"de {mes}"
    return f"{dia}, {moment.day} {de_mes} de {moment.year}"


@eina("Diu la data i l'hora d'ara mateix.")
def data_i_hora():
    ara = datetime.now()
    return f"Avui és {data_en_catala(ara)}, i són les {ara.strftime('%H:%M')}."


@eina("Desa una nota que l'usuari vol apuntar (per a recordatoris amb hora, fes servir "
      "afegir_recordatori).",
      parametres={"text": text("El text de la nota")})
def desar_nota(text):
    moment = datetime.now().strftime("%d/%m/%Y %H:%M")
    with open(FITXER_NOTES, "a", encoding="utf-8") as f:
        f.write(f"[{moment}] {text}\n")
    return "Nota desada."


@eina("Llegeix totes les notes que l'usuari ha desat.")
def llegir_notes():
    if not FITXER_NOTES.exists():
        return "Encara no hi ha cap nota desada."
    with open(FITXER_NOTES, "r", encoding="utf-8") as f:
        notes = f.read().strip()
    return notes or "Encara no hi ha cap nota desada."
