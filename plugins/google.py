# plugins/google.py
# Google Calendar, Gmail, Drive, Tasks i Contactes amb les API oficials de Google.
#
# Per connectar-ho cal, una sola vegada:
#   1. Crear un "client OAuth" d'escriptori a Google Cloud (ho explica GUIA-GOOGLE.md)
#      i desar-lo com a google_credencials.json a la carpeta de JARVIS.
#   2. Dir-li a JARVIS "connecta Google": s'obre el navegador, l'usuari inicia
#      sessió i dona permís. El permís queda desat a google_token.json. Mentrestant
#      la conversació continua, i quan acaba JARVIS ho diu (amb context.avisar).
# JARVIS mai veu la contrasenya: només rep el permís que Google li dona.

import base64
import re
import threading
from datetime import date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formatdate, parsedate_to_datetime
from html import unescape

from config import CARPETA
from eines import context, eina, enter, llista, text

DESCRIPCIO = "Google Calendar, Gmail, Drive, Tasks i Contactes"

CREDENCIALS = CARPETA / "google_credencials.json"
TOKEN = CARPETA / "google_token.json"
PERMISOS = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.modify",      # llegir, enviar i esborranys (no esborra per sempre)
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",        # només els fitxers que crea JARVIS
    "https://www.googleapis.com/auth/tasks",
    "https://www.googleapis.com/auth/contacts.readonly",
]

_serveis = {}
_connectant = threading.Lock()     # agafat mentre el navegador espera que l'usuari doni permís


class NoConnectat(Exception):
    pass


def _credencials():
    """El permís desat a google_token.json (el renova si ha caducat)."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), PERMISOS)
    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN.write_text(creds.to_json(), encoding="utf-8")
            return creds
        except Exception:
            pass
    raise NoConnectat()


def _flux_navegador():
    """Obre el navegador perquè l'usuari doni permís i desa el permís nou. Pot tardar
    fins a 5 minuts (el que l'usuari trigui a fer-ho)."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    flux = InstalledAppFlow.from_client_secrets_file(str(CREDENCIALS), PERMISOS)
    creds = flux.run_local_server(port=0, open_browser=True, timeout_seconds=300,
                                  success_message="JARVIS ja està connectat a Google. Pots tancar aquesta pestanya.")
    TOKEN.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _servei(nom, versio):
    if nom not in _serveis:
        from googleapiclient.discovery import build
        _serveis[nom] = build(nom, versio, credentials=_credencials(), cache_discovery=False)
    return _serveis[nom]


def _amb_google(funcio):
    """Converteix els errors de connexió en frases que l'assistent pugui dir."""
    def embolcall(*args, **kwargs):
        try:
            return funcio(*args, **kwargs)
        except NoConnectat:
            return ("Google encara no està connectat. Digues a l'usuari que, si vol, li pots "
                    "connectar ara amb connectar_google (s'obrirà el navegador).")
        except FileNotFoundError as e:
            return str(e)
        except Exception as e:
            return f"Google ha tornat un error: {e}"
    embolcall.__name__ = funcio.__name__
    embolcall.__doc__ = funcio.__doc__
    embolcall.__wrapped__ = funcio      # perquè @eina vegi els paràmetres reals
    return embolcall


@eina("Connecta (o torna a connectar) JARVIS amb el compte de Google de l'usuari (Calendar, "
      "Gmail, Drive...). S'obre el navegador perquè l'usuari iniciï sessió i doni permís; "
      "quan acabi, rebràs un [AVÍS] amb el resultat. Només cal fer-ho una vegada.")
def connectar_google():
    if not CREDENCIALS.exists():
        return "Falta google_credencials.json a la carpeta de JARVIS. Segueix GUIA-GOOGLE.md per crear-lo."
    if not _connectant.acquire(blocking=False):
        return "El navegador ja està obert per connectar Google: digues a l'usuari que ho acabi allà."
    # El navegador pot tardar minuts: ho fem en un altre fil perquè la conversació no
    # es quedi aturada esperant, i avisem quan acabi.
    threading.Thread(target=_connectar_en_segon_pla, daemon=True).start()
    return ("S'està obrint el navegador. Digues a l'usuari que hi triï el seu compte de Google i "
            "doni tots els permisos (té 5 minuts), i que l'avisaràs quan estigui connectat.")


def _connectar_en_segon_pla():
    try:
        creds = _flux_navegador()
        _serveis.clear()
        from googleapiclient.discovery import build
        perfil = build("gmail", "v1", credentials=creds, cache_discovery=False).users().getProfile(userId="me").execute()
        context.avisar(f"Google ja està connectat amb el compte {perfil['emailAddress']}.")
    except Exception as e:
        context.missatge("err", f"Connexió amb Google: {e}")
        context.avisar("No s'ha completat la connexió amb Google (s'ha acabat el temps o no s'ha "
                       "donat permís). Es pot tornar a provar quan vulguis.")
    finally:
        _connectant.release()


# ─────────────────────────────────────────────────────────────────────────────
#  Google Calendar
# ─────────────────────────────────────────────────────────────────────────────

def _rfc3339(valor):
    valor = valor.strip().replace(" ", "T")
    if len(valor) == 10:
        return None, valor                         # tot el dia
    moment = datetime.fromisoformat(valor[:16]).astimezone()
    return moment.isoformat(), None


@eina("Mostra els esdeveniments del Google Calendar de l'usuari d'un dia o de diversos dies.",
      parametres={"des_de": text("Primer dia, AAAA-MM-DD (per defecte avui)"),
                  "dies": enter("Quants dies (per defecte 1; 7 per a la setmana)")},
      requerits=[])
@_amb_google
def google_calendar_veure(des_de=None, dies=1):
    primer = date.fromisoformat(des_de) if des_de else date.today()
    inici = datetime.combine(primer, datetime.min.time()).astimezone()
    fi = inici + timedelta(days=max(1, int(dies)))
    r = _servei("calendar", "v3").events().list(
        calendarId="primary", timeMin=inici.isoformat(), timeMax=fi.isoformat(),
        singleEvents=True, orderBy="startTime", maxResults=50).execute()
    linies = []
    for e in r.get("items", []):
        s = e["start"].get("dateTime", e["start"].get("date"))
        quan = s[:10] + (" " + s[11:16] if "T" in s else " (tot el dia)")
        lloc = f" — {e['location']}" if e.get("location") else ""
        linies.append(f"{quan} {e.get('summary', '(sense títol)')}{lloc} [id {e['id']}]")
    return "\n".join(linies) or "No hi ha res al Google Calendar en aquests dies."


@eina("Crea un esdeveniment al Google Calendar de l'usuari. Si hi ha convidats, Google els "
      "envia una invitació per correu.",
      parametres={"titol": text("Títol"),
                  "inici": text("Inici, AAAA-MM-DDTHH:MM (o AAAA-MM-DD si és tot el dia)"),
                  "durada_minuts": enter("Durada en minuts (per defecte 60)"),
                  "lloc": text("Lloc (opcional)"),
                  "descripcio": text("Descripció (opcional)"),
                  "convidats": llista("Correus dels convidats (opcional)")},
      requerits=["titol", "inici"],
      perillosa=lambda a: bool(a.get("convidats")),
      resum=lambda a: f"Crear «{a.get('titol')}» al Google Calendar i enviar invitació a: "
                      + ", ".join(a.get("convidats") or []))
@_amb_google
def google_calendar_crear(titol, inici, durada_minuts=60, lloc="", descripcio="", convidats=None):
    moment, dia = _rfc3339(inici)
    cos = {"summary": titol, "location": lloc, "description": descripcio}
    if dia:
        cos["start"] = {"date": dia}
        cos["end"] = {"date": (date.fromisoformat(dia) + timedelta(days=1)).isoformat()}
    else:
        fi = datetime.fromisoformat(moment) + timedelta(minutes=int(durada_minuts))
        cos["start"], cos["end"] = {"dateTime": moment}, {"dateTime": fi.isoformat()}
    if convidats:
        cos["attendees"] = [{"email": c} for c in convidats]
    e = _servei("calendar", "v3").events().insert(
        calendarId="primary", body=cos, sendUpdates="all" if convidats else "none").execute()
    return f"Creat al Google Calendar: «{titol}» [id {e['id']}]."


@eina("Esborra un esdeveniment del Google Calendar pel seu id (surt a google_calendar_veure).",
      parametres={"id": text("Id de l'esdeveniment")},
      perillosa=True, resum=lambda a: "Esborrar un esdeveniment del Google Calendar")
@_amb_google
def google_calendar_esborrar(id):
    _servei("calendar", "v3").events().delete(calendarId="primary", eventId=id).execute()
    return "Esdeveniment esborrat del Google Calendar."


# ─────────────────────────────────────────────────────────────────────────────
#  Gmail
# ─────────────────────────────────────────────────────────────────────────────

def _capcalera(missatge, nom):
    for h in missatge["payload"].get("headers", []):
        if h["name"].lower() == nom.lower():
            return h["value"]
    return ""


def _data_local(capcalera_date):
    """'Sun, 25 Oct 2026 16:56:03 -0700' → '2026-10-26 00:56' (hora de l'ordinador)."""
    try:
        return parsedate_to_datetime(capcalera_date).astimezone().strftime("%Y-%m-%d %H:%M")
    except Exception:
        return capcalera_date[:22]


def _cos(part):
    """Busca el text del correu dins de les parts del missatge."""
    if part.get("mimeType") == "text/plain" and part["body"].get("data"):
        return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
    for p in part.get("parts", []):
        t = _cos(p)
        if t:
            return t
    if part.get("mimeType") == "text/html" and part["body"].get("data"):
        html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", "replace")
        return unescape(re.sub(r"<[^>]+>", " ", html))
    return ""


@eina("Busca correus a Gmail. Fes servir la sintaxi de cerca de Gmail: per exemple "
      "'is:unread' (no llegits), 'from:maria', 'subject:examen', 'newer_than:2d'. "
      "Per defecte mostra els no llegits de la safata d'entrada.",
      parametres={"consulta": text("La cerca, en sintaxi de Gmail"),
                  "quants": enter("Quants correus (per defecte 8)")},
      requerits=[])
@_amb_google
def gmail_cercar(consulta="is:unread in:inbox", quants=8):
    g = _servei("gmail", "v1").users()
    r = g.messages().list(userId="me", q=consulta, maxResults=int(quants)).execute()
    linies = []
    for m in r.get("messages", []):
        msg = g.messages().get(userId="me", id=m["id"], format="metadata",
                               metadataHeaders=["From", "Subject", "Date"]).execute()
        linies.append(f"De: {_capcalera(msg, 'From')} | Assumpte: {_capcalera(msg, 'Subject')} | "
                      f"{_data_local(_capcalera(msg, 'Date'))}\n   {msg.get('snippet', '')[:150]} [id {m['id']}]")
    return "\n".join(linies) or f"No hi ha cap correu per a «{consulta}»."


@eina("Llegeix sencer un correu de Gmail pel seu id (surt a gmail_cercar).",
      parametres={"id": text("Id del correu")})
@_amb_google
def gmail_llegir(id):
    msg = _servei("gmail", "v1").users().messages().get(userId="me", id=id, format="full").execute()
    cos = re.sub(r"\n{3,}", "\n\n", _cos(msg["payload"]).strip())
    return (f"De: {_capcalera(msg, 'From')}\nPer a: {_capcalera(msg, 'To')}\n"
            f"Assumpte: {_capcalera(msg, 'Subject')}\nData: {_data_local(_capcalera(msg, 'Date'))}\n\n{cos[:8000]}")


def _correu(per, assumpte, cos, respondre_a=None):
    g = _servei("gmail", "v1").users()
    m = EmailMessage()
    m["To"] = ", ".join(per) if isinstance(per, list) else per
    m["Subject"] = assumpte
    m["Date"] = formatdate(localtime=True)     # si no, Gmail hi posa l'hora d'un altre fus horari
    m.set_content(cos)
    cos_api = {}
    if respondre_a:
        original = g.messages().get(userId="me", id=respondre_a, format="metadata",
                                    metadataHeaders=["Message-ID", "Subject"]).execute()
        id_msg = _capcalera(original, "Message-ID")
        if id_msg:
            m["In-Reply-To"] = m["References"] = id_msg
        cos_api["threadId"] = original["threadId"]
    cos_api["raw"] = base64.urlsafe_b64encode(m.as_bytes()).decode()
    return g, cos_api


@eina("Envia un correu des del Gmail de l'usuari. L'usuari el confirmarà a la finestra de "
      "confirmació: crida l'eina directament, sense preguntar-li abans si hi està d'acord. "
      "Per respondre un correu, posa el seu id a respondre_a.",
      parametres={"per": text("Correu del destinatari (o diversos separats per comes)"),
                  "assumpte": text("Assumpte"),
                  "cos": text("Text del correu"),
                  "respondre_a": text("Id del correu que es respon (opcional)")},
      requerits=["per", "assumpte", "cos"],
      perillosa=True,
      resum=lambda a: f"Enviar un correu a {a.get('per')}\nAssumpte: {a.get('assumpte')}\n\n{a.get('cos', '')[:600]}")
@_amb_google
def gmail_enviar(per, assumpte, cos, respondre_a=None):
    g, cos_api = _correu(per, assumpte, cos, respondre_a)
    g.messages().send(userId="me", body=cos_api).execute()
    return f"Correu enviat a {per}."


@eina("Desa un esborrany a Gmail (no s'envia; l'usuari el pot revisar i enviar després).",
      parametres={"per": text("Destinatari"), "assumpte": text("Assumpte"), "cos": text("Text"),
                  "respondre_a": text("Id del correu que es respon (opcional)")},
      requerits=["per", "assumpte", "cos"])
@_amb_google
def gmail_esborrany(per, assumpte, cos, respondre_a=None):
    g, cos_api = _correu(per, assumpte, cos, respondre_a)
    msg = {"raw": cos_api["raw"]}
    if "threadId" in cos_api:
        msg["threadId"] = cos_api["threadId"]
    g.drafts().create(userId="me", body={"message": msg}).execute()
    return "Esborrany desat a Gmail."


# ─────────────────────────────────────────────────────────────────────────────
#  Google Drive
# ─────────────────────────────────────────────────────────────────────────────

TIPUS = {"application/vnd.google-apps.document": "Document", "application/vnd.google-apps.spreadsheet": "Full de càlcul",
         "application/vnd.google-apps.presentation": "Presentació", "application/vnd.google-apps.folder": "Carpeta",
         "application/pdf": "PDF",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "Excel",
         "application/vnd.openxmlformats-officedocument.presentationml.presentation": "PowerPoint"}


@eina("Busca fitxers al Google Drive de l'usuari pel nom o pel contingut.",
      parametres={"cerca": text("Paraules del nom o del contingut")})
@_amb_google
def drive_cercar(cerca):
    q = cerca.replace("'", "\\'")
    r = _servei("drive", "v3").files().list(
        q=f"(name contains '{q}' or fullText contains '{q}') and trashed = false",
        pageSize=15, orderBy="modifiedTime desc",
        fields="files(id,name,mimeType,modifiedTime,webViewLink)").execute()
    linies = [f"{f['name']} ({TIPUS.get(f['mimeType'], f['mimeType'].split('/')[-1])}, "
              f"{f['modifiedTime'][:10]}) [id {f['id']}]" for f in r.get("files", [])]
    return "\n".join(linies) or f"No hi ha res al Drive que coincideixi amb «{cerca}»."


@eina("Llegeix el contingut d'un fitxer de Google Drive (Documents, Fulls de càlcul, "
      "Presentacions, Word, PDF o text) pel seu id.",
      parametres={"id": text("Id del fitxer (surt a drive_cercar)")})
@_amb_google
def drive_llegir(id):
    d = _servei("drive", "v3").files()
    info = d.get(fileId=id, fields="name,mimeType").execute()
    exportar = {"application/vnd.google-apps.document": "text/plain",
                "application/vnd.google-apps.spreadsheet": "text/csv",
                "application/vnd.google-apps.presentation": "text/plain"}
    if info["mimeType"] in exportar:
        dades = d.export(fileId=id, mimeType=exportar[info["mimeType"]]).execute()
    elif info["mimeType"].startswith("text/") or info["mimeType"] == "application/json":
        dades = d.get_media(fileId=id).execute()
    elif info["mimeType"] == "application/pdf":
        import io
        from pypdf import PdfReader
        lector = PdfReader(io.BytesIO(d.get_media(fileId=id).execute()))
        dades = "\n".join((p.extract_text() or "") for p in lector.pages[:30]).encode()
    elif info["mimeType"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        # Un Word pujat al Drive (no és un Document de Google): el baixem i el llegim com fitxers.py
        import io
        import docx
        document = docx.Document(io.BytesIO(d.get_media(fileId=id).execute()))
        dades = "\n".join(par.text for par in document.paragraphs).encode()
    else:
        return f"No sé llegir fitxers de tipus {info['mimeType']}."
    contingut = dades.decode("utf-8", "replace") if isinstance(dades, bytes) else str(dades)
    return f"{info['name']}:\n{contingut[:12000]}"


@eina("Crea un Document de Google nou al Drive de l'usuari amb el text indicat.",
      parametres={"titol": text("Títol del document"), "contingut": text("Text del document")})
@_amb_google
def drive_crear_document(titol, contingut):
    from googleapiclient.http import MediaInMemoryUpload
    f = _servei("drive", "v3").files().create(
        body={"name": titol, "mimeType": "application/vnd.google-apps.document"},
        media_body=MediaInMemoryUpload(contingut.encode("utf-8"), mimetype="text/plain"),
        fields="id,webViewLink").execute()
    return f"Document creat: {f['webViewLink']}"


# ─────────────────────────────────────────────────────────────────────────────
#  Google Tasks i Contactes
# ─────────────────────────────────────────────────────────────────────────────

@eina("Mostra les tasques pendents de Google Tasks.")
@_amb_google
def google_tasques_veure():
    t = _servei("tasks", "v1")
    linies = []
    for llista_ in t.tasklists().list(maxResults=10).execute().get("items", []):
        for x in t.tasks().list(tasklist=llista_["id"], showCompleted=False).execute().get("items", []):
            limit = f" (per al {x['due'][:10]})" if x.get("due") else ""
            linies.append(f"{x['title']}{limit} — llista {llista_['title']} [id {x['id']}]")
    return "\n".join(linies) or "No hi ha cap tasca pendent a Google Tasks."


@eina("Afegeix una tasca a Google Tasks.",
      parametres={"titol": text("La tasca"), "data_limit": text("Per a quan, AAAA-MM-DD (opcional)")})
@_amb_google
def google_tasques_afegir(titol, data_limit=None):
    cos = {"title": titol}
    if data_limit:
        cos["due"] = f"{data_limit}T00:00:00.000Z"
    _servei("tasks", "v1").tasks().insert(tasklist="@default", body=cos).execute()
    return f"Tasca afegida a Google Tasks: {titol}."


@eina("Marca com a feta una tasca de Google Tasks pel seu id.",
      parametres={"id": text("Id de la tasca")})
@_amb_google
def google_tasques_completar(id):
    t = _servei("tasks", "v1")
    for llista_ in t.tasklists().list(maxResults=10).execute().get("items", []):
        try:
            t.tasks().patch(tasklist=llista_["id"], task=id, body={"status": "completed"}).execute()
            return "Tasca marcada com a feta."
        except Exception:
            continue
    return "No he trobat la tasca."


@eina("Busca un contacte de Google per nom i en dona el correu i el telèfon.",
      parametres={"nom": text("Nom del contacte")})
@_amb_google
def contactes_google(nom):
    p = _servei("people", "v1").people()
    p.searchContacts(query="", readMask="names").execute()   # Google demana "escalfar" la cerca
    r = p.searchContacts(query=nom, readMask="names,emailAddresses,phoneNumbers", pageSize=10).execute()
    linies = []
    for x in r.get("results", []):
        persona = x["person"]
        noms = ", ".join(n["displayName"] for n in persona.get("names", []))
        correus = ", ".join(e["value"] for e in persona.get("emailAddresses", []))
        telefons = ", ".join(t["value"] for t in persona.get("phoneNumbers", []))
        linies.append(f"{noms}: {correus or 'sense correu'}; {telefons or 'sense telèfon'}")
    return "\n".join(linies) or f"No he trobat cap contacte que es digui «{nom}»."
