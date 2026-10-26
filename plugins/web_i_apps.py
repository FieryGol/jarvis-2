# plugins/web_i_apps.py
# El temps, notícies, YouTube, Spotify i WhatsApp. Cap d'aquestes eines necessita
# cap clau: fan servir serveis públics o els enllaços de les aplicacions.

import re
import time
import webbrowser
import xml.etree.ElementTree as ET
from urllib.parse import quote, quote_plus

import requests

from eines import boolea, eina, enter, text

DESCRIPCIO = "El temps, notícies, YouTube, Spotify i WhatsApp"

CAPCALERES = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) JARVIS2"}

CODIS_TEMPS = {
    0: "cel serè", 1: "gairebé serè", 2: "parcialment ennuvolat", 3: "ennuvolat",
    45: "boira", 48: "boira gebradora", 51: "plugim feble", 53: "plugim", 55: "plugim intens",
    61: "pluja feble", 63: "pluja", 65: "pluja forta", 71: "neu feble", 73: "neu", 75: "neu forta",
    80: "ruixats febles", 81: "ruixats", 82: "ruixats forts", 95: "tempesta",
    96: "tempesta amb calamarsa", 99: "tempesta forta amb calamarsa",
}


@eina("Diu el temps que fa i la previsió dels pròxims dies en una població (Open-Meteo).",
      parametres={"lloc": text("Població, per exemple 'Barcelona' o 'Girona'"),
                  "dies": enter("Quants dies de previsió (1 a 7, per defecte 3)")},
      requerits=["lloc"])
def el_temps(lloc, dies=3):
    geo = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                       params={"name": lloc, "count": 1, "language": "ca"},
                       headers=CAPCALERES, timeout=10).json()
    if not geo.get("results"):
        return f"No he trobat la població «{lloc}»."
    g = geo["results"][0]
    dades = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m,relative_humidity_2m",
        "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": max(1, min(7, int(dies))),
    }, headers=CAPCALERES, timeout=10).json()
    ara = dades["current"]
    text_ = (f"Ara a {g['name']}: {ara['temperature_2m']:.0f} °C (sensació de "
             f"{ara['apparent_temperature']:.0f} °C), {CODIS_TEMPS.get(ara['weather_code'], 'temps variable')}, "
             f"vent de {ara['wind_speed_10m']:.0f} km/h, humitat del {ara['relative_humidity_2m']}%.")
    d = dades["daily"]
    for i, dia in enumerate(d["time"]):
        text_ += (f"\n{dia}: {CODIS_TEMPS.get(d['weather_code'][i], 'variable')}, "
                  f"{d['temperature_2m_min'][i]:.0f}–{d['temperature_2m_max'][i]:.0f} °C, "
                  f"probabilitat de pluja {d['precipitation_probability_max'][i]}%.")
    return text_


@eina("Busca les últimes notícies sobre un tema (o les més importants si no es diu cap tema) "
      "a Google Notícies.",
      parametres={"tema": text("Tema de les notícies (opcional)"),
                  "quantes": enter("Quantes notícies (per defecte 6)")})
def noticies(tema="", quantes=6):
    if tema:
        url = f"https://news.google.com/rss/search?q={quote_plus(tema)}&hl=es&gl=ES&ceid=ES:es"
    else:
        url = "https://news.google.com/rss?hl=es&gl=ES&ceid=ES:es"
    arrel = ET.fromstring(requests.get(url, headers=CAPCALERES, timeout=10).content)
    elements = arrel.findall(".//item")[:int(quantes)]
    if not elements:
        return "No he trobat notícies."
    return "\n".join(f"- {e.findtext('title')} ({e.findtext('pubDate', '')[:16]})" for e in elements)


@eina("Busca un vídeo o una cançó a YouTube i el posa directament (obre el primer resultat "
      "al navegador).",
      parametres={"cerca": text("Què s'ha de buscar")})
def reproduir_youtube(cerca):
    pagina = requests.get("https://www.youtube.com/results", params={"search_query": cerca},
                          headers=CAPCALERES, timeout=10).text
    ids = re.findall(r'"videoId":"([\w-]{11})"', pagina)
    if not ids:
        webbrowser.open("https://www.youtube.com/results?search_query=" + quote_plus(cerca))
        return "No he pogut triar un vídeo; t'he obert la cerca de YouTube."
    webbrowser.open(f"https://www.youtube.com/watch?v={ids[0]}")
    return f"He posat a YouTube el primer resultat de «{cerca}»."


@eina("Busca una cançó, un artista o una llista a Spotify (obre l'aplicació amb la cerca). "
      "Per posar en pausa o passar cançó, fes servir control_multimedia.",
      parametres={"cerca": text("Cançó, artista o llista")})
def buscar_spotify(cerca):
    import os
    try:
        os.startfile("spotify:search:" + quote(cerca))
        return f"He obert Spotify amb la cerca «{cerca}». Fes clic al resultat per escoltar-lo."
    except Exception:
        webbrowser.open("https://open.spotify.com/search/" + quote(cerca))
        return f"No tinc l'aplicació de Spotify; he obert «{cerca}» a Spotify web."


@eina("Prepara un missatge de WhatsApp per a un número de telèfon. Si enviar és cert, "
      "l'envia; si no, el deixa escrit perquè l'usuari el revisi. Per saber el número d'un "
      "contacte, fes servir contactes_google si està connectat o pregunta-ho.",
      parametres={"telefon": text("Número amb prefix, per exemple 34600111222"),
                  "missatge": text("El text del missatge"),
                  "enviar": boolea("Enviar-lo directament")},
      requerits=["telefon", "missatge"],
      perillosa=lambda a: bool(a.get("enviar")),
      resum=lambda a: f"Enviar per WhatsApp al {a.get('telefon', '')}:\n«{a.get('missatge', '')}»")
def whatsapp(telefon, missatge, enviar=False):
    import os
    numero = re.sub(r"\D", "", telefon)
    if len(numero) == 9:
        numero = "34" + numero         # si no porta prefix, suposem Espanya
    try:
        os.startfile(f"whatsapp://send?phone={numero}&text={quote(missatge)}")
    except Exception:
        webbrowser.open(f"https://wa.me/{numero}?text={quote(missatge)}")
        return "No tinc l'aplicació de WhatsApp: t'he obert WhatsApp Web amb el missatge preparat."
    if enviar:
        import pyautogui
        time.sleep(4)              # que tingui temps d'obrir el xat
        pyautogui.press("enter")
        return "Missatge enviat per WhatsApp."
    return "T'he deixat el missatge escrit a WhatsApp. Revisa'l i prem Retorn per enviar-lo."
