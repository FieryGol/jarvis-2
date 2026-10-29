# plugins/terra.py
# «Ensenya'm el món»: un globus terraqüi en 3D dins la finestra de JARVIS (globus.py),
# en mode holograma o amb fotos de satèl·lit, que vola a qualsevol lloc i mostra els
# terratrèmols de les últimes 24 hores i on és l'Estació Espacial Internacional.
# Si falta la biblioteca PyQt6-WebEngine, obre Google Earth al navegador.
# Cap servei necessita clau: OpenStreetMap (per trobar llocs), Esri, USGS i wheretheiss.at.

import random
import webbrowser
from urllib.parse import quote

import requests

from eines import eina, opcions, text

DESCRIPCIO = "Globus terraqüi 3D: llocs, terratrèmols i l'ISS"

CAPCALERES = {"User-Agent": "JARVIS2 (github.com/FieryGol/jarvis-2)"}   # OpenStreetMap ho demana
MODES = ["holograma", "satel·lit"]

# Llocs per a «sorprèn-me» (es veuen molt bé des de dalt)
LLOCS_SORPRESA = [
    "Grand Canyon", "Machu Picchu", "Torre Eiffel, París", "Mont Everest",
    "Sagrada Família, Barcelona", "Piràmides de Gizeh", "Opera de Sydney", "Mont Fuji",
    "Cataratas del Iguazú", "Colosseu, Roma", "Central Park, Nova York", "Santorini",
    "Petra, Jordània", "Montserrat", "Taj Mahal", "Cristo Redentor, Rio de Janeiro",
    "Geirangerfjord", "Uluru", "Golden Gate Bridge", "Burj Khalifa, Dubai",
]

_context = None


def _globus(**dades):
    """Envia una ordre al globus de la finestra. Torna False si no n'hi ha."""
    import globus
    if _context is None or not globus.disponible():
        return False
    _context.interficie("globus", dades)
    return True


def _buscar(lloc):
    """Troba les coordenades d'un lloc (ciutat, monument, adreça...) amb OpenStreetMap."""
    r = requests.get("https://nominatim.openstreetmap.org/search",
                     params={"q": lloc, "format": "json", "limit": 1, "accept-language": "ca"},
                     headers=CAPCALERES, timeout=10)
    resultats = r.json()
    if not resultats:
        return None
    x = resultats[0]
    sud, nord, oest, est = (float(v) for v in x["boundingbox"])
    # Alçada de la càmera segons la mida del lloc: un país es veu de lluny, un monument de prop
    graus = max(nord - sud, (est - oest) * 0.8)
    alcada = min(max(graus * 111000 * 1.6, 1200), 9000000)
    nom = x.get("name") or x["display_name"].split(",")[0]
    return float(x["lat"]), float(x["lon"]), alcada, nom, x["display_name"]


@eina("Ensenya el món a l'usuari amb un globus terraqüi en 3D que surt dins la finestra de JARVIS "
      "(com al JARVIS d'Iron Man), i hi pot volar a qualsevol lloc: una ciutat, un país, un "
      "monument, una muntanya, una adreça... Fes-la servir quan digui 'ensenya'm el món', "
      "'mostra'm la Terra', 'porta'm a...', 'vull veure... des de dalt' o 'on és...'. El mode "
      "holograma és blau, estil Iron Man; el de satèl·lit fa servir fotos reals (i amb molt de "
      "zoom es veuen els carrers). Si després vol que li expliquis què s'hi veu, fes servir mirar_pantalla.",
      parametres={"lloc": text("On anar (buit per veure tota la Terra)"),
                  "mode": opcions("holograma (blau) o satel·lit (fotos reals). Si l'usuari no ho "
                                  "diu, deixa'l buit", MODES)},
      requerits=[])
def ensenyar_el_mon(lloc="", mode=""):
    mode = mode if mode in MODES else ""
    if not lloc:
        if _globus(accio="inici", mode=mode):
            return "He obert el globus terraqüi a la finestra. Gira sol; l'usuari el pot moure amb el ratolí."
        webbrowser.open("https://earth.google.com/web/")
        return "He obert Google Earth al navegador."
    try:
        trobat = _buscar(lloc)
    except Exception as e:
        return f"No he pogut buscar «{lloc}»: {e}"
    if trobat is None:
        return f"No he trobat cap lloc que es digui «{lloc}». Demana-li que t'ho digui d'una altra manera."
    lat, lon, alcada, nom, complet = trobat
    if _globus(accio="volar", lat=lat, lon=lon, alcada=alcada, nom=nom, mode=mode):
        return f"Volant a {complet} ({lat:.4f}, {lon:.4f}) al globus de la finestra."
    webbrowser.open(f"https://earth.google.com/web/search/{quote(lloc)}")
    return f"He obert Google Earth al navegador a {complet}."


@eina("Porta l'usuari a un lloc espectacular del món triat a l'atzar, al globus de la finestra "
      "en mode satèl·lit. Fes-la servir quan digui 'sorprèn-me' o 'ensenya'm alguna cosa xula del "
      "món'. Després explica-li breument què és aquell lloc.")
def lloc_sorpresa():
    lloc = random.choice(LLOCS_SORPRESA)
    resultat = ensenyar_el_mon(lloc, "satel·lit")
    return f"{resultat} Explica-li a l'usuari breument què és {lloc} i per què és especial."


@eina("Diu els terratrèmols forts (magnitud 4,5 o més) de les últimes 24 hores a tot el món, "
      "segons l'USGS, i els mostra al globus (són els punts taronja). Pot volar al més fort.")
def terratremols_recents():
    dades = requests.get("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson",
                         timeout=10).json()
    sismes = sorted(dades["features"], key=lambda f: f["properties"]["mag"], reverse=True)
    if not sismes:
        return "No hi ha hagut cap terratrèmol de magnitud 4,5 o més en les últimes 24 hores."
    fort = sismes[0]
    lon, lat = fort["geometry"]["coordinates"][:2]
    _globus(accio="volar", lat=lat, lon=lon, alcada=2500000,
            nom=f"M{fort['properties']['mag']:.1f} · {fort['properties']['place']}")
    linies = [f"M{f['properties']['mag']:.1f} — {f['properties']['place']}" for f in sismes[:6]]
    return (f"{len(sismes)} terratrèmols de magnitud 4,5 o més en les últimes 24 hores. Els més forts:\n"
            + "\n".join(linies))


@eina("Diu on és ara mateix l'Estació Espacial Internacional (ISS) i la mostra al globus amb la seva òrbita.")
def on_es_la_iss():
    p = requests.get("https://api.wheretheiss.at/v1/satellites/25544", timeout=10).json()
    _globus(accio="iss")
    return (f"L'ISS és ara a {p['latitude']:.2f}, {p['longitude']:.2f}, a {p['altitude']:.0f} km d'alçada, "
            f"anant a {p['velocity']:.0f} km/h (fa una volta a la Terra cada 92 minuts). "
            f"És de {'dia' if p['visibility'] == 'daylight' else 'nit'} allà on és.")


@eina("Tanca el globus terraqüi de la finestra.")
def tancar_el_mon():
    if _globus(accio="tancar"):
        return "He tancat el globus."
    return "El globus no estava obert."


def iniciar(context):
    global _context
    _context = context
