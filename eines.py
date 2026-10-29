# eines.py
# El registre d'"eines": les funcions de Python que Gemini pot demanar que executem.
#
# Com funciona:
#   1. Cada plugin (un fitxer de la carpeta plugins/) defineix funcions i les
#      marca amb @eina(...). Això les apunta al registre EINES.
#   2. Li expliquem a Gemini quines eines hi ha (declaracions()).
#   3. Quan l'usuari diu "obre la calculadora", Gemini no l'obre ell: ens envia
#      "executa obrir_aplicacio amb nom='calculadora'".
#   4. assistent.py busca l'eina al registre, demana permís si és perillosa,
#      l'executa i li torna el resultat a Gemini.
#
# Per afegir una eina nova n'hi ha prou amb escriure-la en un plugin:
#
#     from eines import eina, text
#
#     @eina("Tira un dau de sis cares.")
#     def tirar_dau():
#         return f"Ha sortit un {random.randint(1, 6)}."

import importlib
import pkgutil
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable


# ─────────────────────────────────────────────────────────────────────────────
#  Com es descriuen els paràmetres (el format que entén Gemini)
# ─────────────────────────────────────────────────────────────────────────────

def text(descripcio):
    return {"type": "STRING", "description": descripcio}


def enter(descripcio):
    return {"type": "INTEGER", "description": descripcio}


def decimal(descripcio):
    return {"type": "NUMBER", "description": descripcio}


def boolea(descripcio):
    return {"type": "BOOLEAN", "description": descripcio}


def opcions(descripcio, valors):
    """Un text que només pot ser un dels valors de la llista."""
    return {"type": "STRING", "description": descripcio, "enum": list(valors)}


def llista(descripcio, element=None):
    return {"type": "ARRAY", "description": descripcio,
            "items": element or {"type": "STRING"}}


# ─────────────────────────────────────────────────────────────────────────────
#  El registre
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class Eina:
    nom: str
    descripcio: str
    funcio: Callable
    parametres: dict = field(default_factory=dict)
    requerits: list = field(default_factory=list)
    # True, False o una funció que rep els arguments i diu si és perillosa
    # (per exemple, crear un fitxer només és perillós si en sobreescriu un).
    perillosa: Any = False
    # Una funció que rep els arguments i torna una frase per a la finestra de
    # confirmació ("Esborrar el fitxer informe.docx").
    resum: Callable | None = None
    plugin: str = ""
    asincrona: bool = False      # les eines MCP i les de la càmera són async

    def es_perillosa(self, arguments):
        if callable(self.perillosa):
            return bool(self.perillosa(arguments))
        return bool(self.perillosa)

    def declaracio(self):
        d = {"name": self.nom, "description": self.descripcio}
        if self.parametres:
            d["parameters"] = {"type": "OBJECT", "properties": self.parametres}
            if self.requerits:
                d["parameters"]["required"] = list(self.requerits)
        return d


EINES: dict[str, Eina] = {}
PLUGINS: dict[str, str] = {}     # nom del plugin → descripció curta (o l'error)


def registrar(e):
    EINES[e.nom] = e


def eina(descripcio, parametres=None, requerits=None, perillosa=False, resum=None):
    """Decorador: apunta la funció al registre d'eines."""
    def decorador(funcio):
        modul = funcio.__module__.split(".")[-1]
        registrar(Eina(
            nom=funcio.__name__,
            descripcio=descripcio,
            funcio=funcio,
            parametres=parametres or {},
            # si no es diu res, els paràmetres sense valor per defecte són obligatoris
            requerits=requerits if requerits is not None else _sense_valor_per_defecte(funcio),
            perillosa=perillosa,
            resum=resum,
            plugin=modul,
        ))
        return funcio
    return decorador


def _sense_valor_per_defecte(funcio):
    import inspect
    return [n for n, p in inspect.signature(funcio).parameters.items()
            if p.default is inspect.Parameter.empty]


# ─────────────────────────────────────────────────────────────────────────────
#  Coses que els plugins poden fer servir
# ─────────────────────────────────────────────────────────────────────────────

class AmbImatge:
    """Resultat d'una eina que també porta una imatge (per exemple una captura
    de pantalla). assistent.py envia la imatge a Gemini perquè la pugui veure."""

    def __init__(self, text, jpeg):
        self.text = text
        self.jpeg = jpeg


class Context:
    """El que assistent.py posa a l'abast dels plugins."""

    def __init__(self):
        self.config = {}
        self.avisar = lambda text: print("[Avís]", text)   # parlar a l'usuari sense que pregunti
        self.missatge = lambda tipus, text: print(f"[{tipus}]", text)
        # Per als plugins que porten l'assistent a un altre lloc (per exemple Telegram):
        self.enviar_text = lambda text, des_del_mobil=False: None   # donar-li una ordre escrita
        self.escoltadors = []        # funcions(tipus, text) que reben tots els missatges del registre
        self.en_confirmacio = []     # funcions(eina, detall, futur) quan cal donar permís


context = Context()


# ─────────────────────────────────────────────────────────────────────────────
#  Carregar els plugins
# ─────────────────────────────────────────────────────────────────────────────

def carregar_plugins(desactivats=()):
    """Importa tots els fitxers de la carpeta plugins/. En importar-los, els
    decoradors @eina apunten les eines al registre."""
    import sys
    import plugins
    if getattr(sys, "frozen", False):
        # Dins del JARVIS2.exe els plugins van empaquetats; a més, carreguem els que
        # l'usuari posi a la carpeta plugins/ del costat de l'.exe.
        from config import CARPETA
        externs = CARPETA / "plugins"
        if externs.is_dir() and str(externs) not in plugins.__path__:
            plugins.__path__.append(str(externs))
    vistos = set()
    for modul in pkgutil.iter_modules(plugins.__path__):
        nom = modul.name
        if nom.startswith("_") or nom in desactivats or nom in vistos:
            continue
        vistos.add(nom)
        try:
            m = importlib.import_module(f"plugins.{nom}")
            PLUGINS[nom] = getattr(m, "DESCRIPCIO", "")
            if hasattr(m, "iniciar"):
                m.iniciar(context)
        except Exception as e:
            # Un plugin que falla (li falta una biblioteca, per exemple) no ha
            # d'impedir que la resta funcionin.
            PLUGINS[nom] = f"ERROR: {e}"
            traceback.print_exc()


def declaracions():
    return [e.declaracio() for e in EINES.values()]


def executar(nom, arguments):
    """Executa una eina normal (no async) i torna el resultat."""
    e = EINES.get(nom)
    if e is None:
        return f"No existeix cap eina que es digui {nom}."
    try:
        return e.funcio(**(arguments or {}))
    except TypeError as err:
        return f"Els paràmetres de {nom} no són correctes: {err}"
    except Exception as err:
        return f"L'eina {nom} ha fallat: {err}"
