# plugins/agenda.py
# L'agenda pròpia de JARVIS: horari (esdeveniments que es poden repetir cada
# setmana), recordatoris amb hora i llista de tasques. Tot es desa a agenda.json.
#
# Un fil (thread) mira cada 15 segons si toca avisar d'alguna cosa. Quan toca,
# crida context.avisar(), i l'assistent ho diu en veu alta.

import json
import threading
import time
from datetime import date, datetime, timedelta

from config import CARPETA
from eines import eina, enter, llista, opcions, text

DESCRIPCIO = "Horari, recordatoris i tasques (agenda.json)"

FITXER = CARPETA / "agenda.json"
DIES = ["dilluns", "dimarts", "dimecres", "dijous", "divendres", "dissabte", "diumenge"]
_bloqueig = threading.Lock()
_context = None


# ─────────────────────────────────────────────────────────────────────────────
#  Llegir i desar
# ─────────────────────────────────────────────────────────────────────────────

def _llegir():
    if FITXER.exists():
        try:
            dades = json.loads(FITXER.read_text(encoding="utf-8"))
        except Exception:
            dades = {}
    else:
        dades = {}
    for clau in ("esdeveniments", "recordatoris", "tasques"):
        dades.setdefault(clau, [])
    dades.setdefault("avisats", {})
    dades.setdefault("seguent_id", 1)
    return dades


def _desar(dades):
    FITXER.write_text(json.dumps(dades, indent=2, ensure_ascii=False), encoding="utf-8")


def _nou_id(dades, lletra):
    n = dades["seguent_id"]
    dades["seguent_id"] = n + 1
    return f"{lletra}{n}"


def _data_hora(valor):
    """Converteix '2026-10-27T09:00' (o '2026-10-27 09:00', o '2026-10-27') en datetime."""
    valor = valor.strip().replace(" ", "T")
    if len(valor) == 10:
        return datetime.fromisoformat(valor + "T00:00"), True    # tot el dia
    return datetime.fromisoformat(valor[:16]), False


def _bonic(moment, tot_el_dia=False):
    dia = DIES[moment.weekday()]
    if tot_el_dia:
        return f"{dia} {moment.day}/{moment.month}"
    return f"{dia} {moment.day}/{moment.month} a les {moment.strftime('%H:%M')}"


# ─────────────────────────────────────────────────────────────────────────────
#  Quins esdeveniments hi ha cada dia (tenint en compte les repeticions)
# ─────────────────────────────────────────────────────────────────────────────

def _passa_el_dia(e, dia):
    inici, _ = _data_hora(e["inici"])
    if dia < inici.date():
        return False
    if e.get("fins") and dia > date.fromisoformat(e["fins"]):
        return False
    rep = e.get("repeticio", "cap")
    if rep == "cap":
        return dia == inici.date()
    if rep == "diaria":
        return True
    if rep == "feiners":
        return dia.weekday() < 5
    if rep == "setmanal":
        dies = e.get("dies") or [DIES[inici.weekday()]]
        return DIES[dia.weekday()] in dies
    return False


def esdeveniments_del_dia(dia, dades=None):
    """Torna [(moment d'inici, esdeveniment)] d'un dia, ordenats per hora."""
    dades = dades or _llegir()
    resultat = []
    for e in dades["esdeveniments"]:
        if _passa_el_dia(e, dia):
            inici, _ = _data_hora(e["inici"])
            resultat.append((datetime.combine(dia, inici.time()), e))
    return sorted(resultat, key=lambda x: x[0])


def propers(quantitat=4):
    """Per a la finestra: els esdeveniments d'avui que encara no han acabat."""
    ara = datetime.now()
    sortida = []
    for moment, e in esdeveniments_del_dia(ara.date()):
        fi = moment + timedelta(minutes=e.get("durada_minuts", 60))
        if fi >= ara:
            sortida.append((moment.strftime("%H:%M") if not e.get("tot_el_dia") else "Tot el dia",
                            e["titol"]))
    return sortida[:quantitat]


# ─────────────────────────────────────────────────────────────────────────────
#  Esdeveniments
# ─────────────────────────────────────────────────────────────────────────────

@eina("Afegeix un esdeveniment a l'agenda o a l'horari de l'usuari (classes, entrenaments, "
      "exàmens, quedades...). Pot repetir-se cada dia, els dies feiners o uns dies concrets "
      "de cada setmana. Fes-la servir també per crear l'horari setmanal de classes.",
      parametres={
          "titol": text("Què és (per exemple 'Classe de mates')"),
          "inici": text("Data i hora del primer cop, format AAAA-MM-DDTHH:MM (o AAAA-MM-DD si és tot el dia)"),
          "durada_minuts": enter("Quant dura, en minuts (per defecte 60)"),
          "repeticio": opcions("Si es repeteix", ["cap", "diaria", "feiners", "setmanal"]),
          "dies": llista("Si és setmanal, quins dies de la setmana",
                         {"type": "STRING", "enum": DIES}),
          "fins": text("Fins a quina data es repeteix, AAAA-MM-DD (opcional)"),
          "lloc": text("On és (opcional)"),
          "avisar_minuts": enter("Quants minuts abans s'ha d'avisar (per defecte 10; 0 per no avisar)"),
      })
def afegir_esdeveniment(titol, inici, durada_minuts=60, repeticio="cap", dies=None,
                        fins=None, lloc="", avisar_minuts=10):
    moment, tot_el_dia = _data_hora(inici)
    dies = list(dict.fromkeys(d.lower() for d in (dies or [])))    # sense repetits
    with _bloqueig:
        dades = _llegir()
        e = {"id": _nou_id(dades, "e"), "titol": titol, "inici": moment.strftime("%Y-%m-%dT%H:%M"),
             "tot_el_dia": tot_el_dia, "durada_minuts": int(durada_minuts), "repeticio": repeticio,
             "dies": dies, "fins": fins, "lloc": lloc, "avisar_minuts": int(avisar_minuts)}
        dades["esdeveniments"].append(e)
        _desar(dades)
    quan = _bonic(moment, tot_el_dia)
    if repeticio == "setmanal":
        quan += f", cada setmana ({', '.join(dies or [DIES[moment.weekday()]])})"
    elif repeticio == "diaria":
        quan += ", cada dia"
    elif repeticio == "feiners":
        quan += ", cada dia feiner"
    return f"Afegit «{titol}» ({e['id']}): {quan}."


@eina("Mostra l'agenda: els esdeveniments, recordatoris i tasques amb data d'un dia o de "
      "diversos dies seguits. Fes-la servir quan l'usuari pregunti què té avui, demà, "
      "aquesta setmana o quin és el seu horari.",
      parametres={
          "des_de": text("Primer dia, format AAAA-MM-DD (per defecte avui)"),
          "dies": enter("Quants dies s'han de mostrar (per defecte 1; 7 per a tota la setmana)"),
      })
def veure_agenda(des_de=None, dies=1):
    dades = _llegir()
    primer = date.fromisoformat(des_de) if des_de else date.today()
    linies = []
    for i in range(max(1, int(dies))):
        dia = primer + timedelta(days=i)
        coses = []        # (hora per ordenar, línia)
        for moment, e in esdeveniments_del_dia(dia, dades):
            hora = "tot el dia" if e.get("tot_el_dia") else moment.strftime("%H:%M")
            lloc = f" ({e['lloc']})" if e.get("lloc") else ""
            coses.append(("" if e.get("tot_el_dia") else hora, f"  {hora} {e['titol']}{lloc} [{e['id']}]"))
        for r in dades["recordatoris"]:
            quan, _ = _data_hora(r["quan"])
            if quan.date() == dia and not r.get("fet"):
                hora = quan.strftime("%H:%M")
                coses.append((hora, f"  {hora} recordatori: {r['text']} [{r['id']}]"))
        for t in dades["tasques"]:
            if t.get("data_limit") == dia.isoformat() and not t.get("feta"):
                coses.append(("99", f"  tasca per entregar: {t['text']} [{t['id']}]"))
        coses = [linia for _, linia in sorted(coses)]
        capcalera = f"{DIES[dia.weekday()]} {dia.day}/{dia.month}:"
        linies.append(capcalera + ("\n" + "\n".join(coses) if coses else " res"))
    return "\n".join(linies)


@eina("Canvia un esdeveniment de l'agenda (títol, hora, durada o lloc). Cal l'identificador "
      "(per exemple e3), que surt a veure_agenda.",
      parametres={"id": text("Identificador de l'esdeveniment"),
                  "titol": text("Títol nou (opcional)"),
                  "inici": text("Data i hora noves, AAAA-MM-DDTHH:MM (opcional)"),
                  "durada_minuts": enter("Durada nova en minuts (opcional)"),
                  "lloc": text("Lloc nou (opcional)")},
      requerits=["id"])
def modificar_esdeveniment(id, titol=None, inici=None, durada_minuts=None, lloc=None):
    with _bloqueig:
        dades = _llegir()
        for e in dades["esdeveniments"]:
            if e["id"] == id:
                if titol:
                    e["titol"] = titol
                if inici:
                    moment, tot = _data_hora(inici)
                    e["inici"], e["tot_el_dia"] = moment.strftime("%Y-%m-%dT%H:%M"), tot
                if durada_minuts:
                    e["durada_minuts"] = int(durada_minuts)
                if lloc is not None:
                    e["lloc"] = lloc
                _desar(dades)
                return f"He canviat «{e['titol']}»."
    return f"No he trobat l'esdeveniment {id}."


def _titol(id):
    dades = _llegir()
    for llista_ in (dades["esdeveniments"], dades["recordatoris"], dades["tasques"]):
        for x in llista_:
            if x["id"] == id:
                return x.get("titol") or x.get("text")
    return id


@eina("Esborra un esdeveniment, un recordatori o una tasca de l'agenda pel seu identificador "
      "(e3, r5, t2...). Si es repeteix, s'esborren totes les vegades.",
      parametres={"id": text("Identificador")},
      perillosa=True, resum=lambda a: f"Esborrar de l'agenda: «{_titol(a.get('id', ''))}»")
def esborrar_de_agenda(id):
    with _bloqueig:
        dades = _llegir()
        for clau in ("esdeveniments", "recordatoris", "tasques"):
            abans = len(dades[clau])
            dades[clau] = [x for x in dades[clau] if x["id"] != id]
            if len(dades[clau]) != abans:
                _desar(dades)
                return f"Esborrat {id}."
    return f"No he trobat {id}."


# ─────────────────────────────────────────────────────────────────────────────
#  Recordatoris i temporitzadors
# ─────────────────────────────────────────────────────────────────────────────

@eina("Posa un recordatori o un temporitzador: a l'hora indicada, JARVIS ho dirà en veu alta. "
      "Indica 'quan' (data i hora) o 'minuts' (d'aquí a quants minuts).",
      parametres={"text": text("Què s'ha de recordar"),
                  "quan": text("Data i hora, AAAA-MM-DDTHH:MM (opcional si poses minuts)"),
                  "minuts": enter("D'aquí a quants minuts (opcional si poses quan)")},
      requerits=["text"])
def afegir_recordatori(text, quan=None, minuts=None):
    if minuts is not None:
        moment = datetime.now() + timedelta(minutes=int(minuts))
    elif quan:
        moment, _ = _data_hora(quan)
    else:
        return "Necessito saber quan: una hora o d'aquí a quants minuts."
    with _bloqueig:
        dades = _llegir()
        r = {"id": _nou_id(dades, "r"), "text": text,
             "quan": moment.strftime("%Y-%m-%dT%H:%M:%S")[:16], "fet": False}
        if minuts is not None:
            r["quan_exacte"] = moment.isoformat(timespec="seconds")
        dades["recordatoris"].append(r)
        _desar(dades)
    return f"D'acord, t'ho recordaré {_bonic(moment)} ({r['id']})."


@eina("Llista els recordatoris pendents.")
def veure_recordatoris():
    pendents = [r for r in _llegir()["recordatoris"] if not r.get("fet")]
    if not pendents:
        return "No hi ha cap recordatori pendent."
    return "\n".join(f"{_bonic(_data_hora(r['quan'])[0])}: {r['text']} [{r['id']}]" for r in pendents)


# ─────────────────────────────────────────────────────────────────────────────
#  Tasques
# ─────────────────────────────────────────────────────────────────────────────

@eina("Afegeix una tasca a la llista de coses per fer (deures, encàrrecs...).",
      parametres={"text": text("La tasca"),
                  "data_limit": text("Per a quan és, AAAA-MM-DD (opcional)")})
def afegir_tasca(text, data_limit=None):
    with _bloqueig:
        dades = _llegir()
        t = {"id": _nou_id(dades, "t"), "text": text, "data_limit": data_limit, "feta": False}
        dades["tasques"].append(t)
        _desar(dades)
    return f"Tasca afegida ({t['id']})."


@eina("Llista les tasques pendents (i les fetes, si es demana).",
      parametres={"incloure_fetes": {"type": "BOOLEAN", "description": "Mostrar també les fetes"}})
def veure_tasques(incloure_fetes=False):
    tasques = [t for t in _llegir()["tasques"] if incloure_fetes or not t.get("feta")]
    if not tasques:
        return "No hi ha cap tasca pendent."
    tasques.sort(key=lambda t: t.get("data_limit") or "9999")
    linies = []
    for t in tasques:
        limit = f" (per al {t['data_limit']})" if t.get("data_limit") else ""
        feta = " ✔" if t.get("feta") else ""
        linies.append(f"{t['text']}{limit}{feta} [{t['id']}]")
    return "\n".join(linies)


@eina("Marca una tasca com a feta.", parametres={"id": text("Identificador de la tasca (t3...)")})
def completar_tasca(id):
    with _bloqueig:
        dades = _llegir()
        for t in dades["tasques"]:
            if t["id"] == id:
                t["feta"] = True
                _desar(dades)
                return f"Fet: «{t['text']}»."
    return f"No he trobat la tasca {id}."


# ─────────────────────────────────────────────────────────────────────────────
#  El fil que avisa
# ─────────────────────────────────────────────────────────────────────────────

def _vigilar():
    while True:
        try:
            _revisar()
        except Exception as e:
            print("[Agenda]", e)
        time.sleep(15)


def _revisar():
    ara = datetime.now()
    avisos = []
    with _bloqueig:
        dades = _llegir()
        canviat = False
        for r in dades["recordatoris"]:
            quan = datetime.fromisoformat(r.get("quan_exacte") or r["quan"])
            if not r.get("fet") and quan <= ara:
                r["fet"] = True
                canviat = True
                # Si fa molta estona que havia de sonar (l'ordinador estava apagat), ho diem
                tard = "" if ara - quan < timedelta(minutes=5) else f" (era per a les {quan.strftime('%H:%M')})"
                avisos.append(f"Recordatori: {r['text']}{tard}")
        for moment, e in esdeveniments_del_dia(ara.date(), dades):
            minuts = e.get("avisar_minuts", 10)
            clau = f"{e['id']}@{ara.date().isoformat()}"
            if e.get("tot_el_dia") or minuts <= 0 or clau in dades["avisats"]:
                continue
            if moment - timedelta(minutes=minuts) <= ara < moment:
                dades["avisats"][clau] = True
                canviat = True
                falten = max(1, round((moment - ara).total_seconds() / 60))
                lloc = f" a {e['lloc']}" if e.get("lloc") else ""
                avisos.append(f"D'aquí {falten} minuts tens «{e['titol']}»{lloc}.")
        # Netegem els avisos d'altres dies
        avui = ara.date().isoformat()
        vells = [k for k in dades["avisats"] if not k.endswith(avui)]
        for k in vells:
            del dades["avisats"][k]
        if canviat or vells:
            _desar(dades)
    for a in avisos:
        _context.avisar(a)


def iniciar(context):
    global _context
    _context = context
    threading.Thread(target=_vigilar, daemon=True).start()
