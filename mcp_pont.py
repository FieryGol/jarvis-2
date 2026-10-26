# mcp_pont.py
# El "pont" MCP: connecta JARVIS amb servidors MCP (Model Context Protocol).
#
# MCP és l'estàndard que fan servir Claude, ChatGPT, Gemini CLI i molts altres
# assistents per connectar-se amb eines externes. A GitHub n'hi ha milers:
# Windows, Google Workspace, Notion, Spotify, navegadors... Cada servidor ofereix
# una llista d'eines; aquest fitxer les converteix en eines de JARVIS.
#
# Els servidors es configuren a mcp_servers.json. Es pot enganxar tal qual el
# bloc "mcpServers" que surt al README de qualsevol servidor MCP.

import io
import json
import os
import re
import shutil
from contextlib import AsyncExitStack

from config import CARPETA
from eines import AmbImatge, Eina, PLUGINS, registrar

FITXER = CARPETA / "mcp_servers.json"
FITXER_REGISTRE = CARPETA / "mcp_registre.log"

TIPUS = {"string": "STRING", "integer": "INTEGER", "number": "NUMBER",
         "boolean": "BOOLEAN", "array": "ARRAY", "object": "OBJECT"}


# ─────────────────────────────────────────────────────────────────────────────
#  Convertir l'esquema JSON d'una eina MCP al format que entén Gemini Live
# ─────────────────────────────────────────────────────────────────────────────
# Les proves van mostrar que Gemini Live s'inventa els noms dels paràmetres si
# se li passa l'esquema JSON tal qual, però els respecta si es fa servir el seu
# format propi (type: "STRING", "OBJECT"...). Per això el convertim.

def convertir_esquema(esq, defs=None, profunditat=0):
    defs = defs if defs is not None else esq.get("$defs", esq.get("definitions", {}))
    if "$ref" in esq:
        nom = esq["$ref"].split("/")[-1]
        esq = {**defs.get(nom, {}), **{k: v for k, v in esq.items() if k != "$ref"}}
    for clau in ("anyOf", "oneOf"):
        if clau in esq:
            opcions = [o for o in esq[clau] if o.get("type") != "null"]
            base = {k: v for k, v in esq.items() if k != clau}
            esq = {**(opcions[0] if opcions else {"type": "string"}), **base}
    if "allOf" in esq:
        junt = {}
        for o in esq["allOf"]:
            junt.update(o)
        esq = {**junt, **{k: v for k, v in esq.items() if k != "allOf"}}

    tipus = esq.get("type", "object" if "properties" in esq else "string")
    if isinstance(tipus, list):
        tipus = next((t for t in tipus if t != "null"), "string")
    resultat = {"type": TIPUS.get(tipus, "STRING")}
    descripcio = esq.get("description") or esq.get("title")
    if descripcio:
        resultat["description"] = str(descripcio)[:500]
    if "enum" in esq and tipus == "string":
        resultat["enum"] = [str(v) for v in esq["enum"]]

    if resultat["type"] == "ARRAY":
        resultat["items"] = convertir_esquema(esq.get("items", {"type": "string"}), defs, profunditat + 1)
    elif resultat["type"] == "OBJECT":
        props = esq.get("properties", {})
        if not props or profunditat > 4:
            # Un objecte "lliure": l'acceptem com a text JSON
            return {"type": "STRING", "description": (descripcio or "") + " (objecte en format JSON)"}
        resultat["properties"] = {n: convertir_esquema(p, defs, profunditat + 1) for n, p in props.items()}
        req = [r for r in esq.get("required", []) if r in props]
        if req:
            resultat["required"] = req
    return resultat


def _nom_valid(text):
    return re.sub(r"[^a-zA-Z0-9_]", "_", text)[:60]


# ─────────────────────────────────────────────────────────────────────────────
#  El pont
# ─────────────────────────────────────────────────────────────────────────────

class PontMCP:
    def __init__(self, missatge):
        self.missatge = missatge          # per escriure al registre de la finestra
        self.pila = AsyncExitStack()
        self.sessions = {}

    def configuracio(self):
        if not FITXER.exists():
            return {}
        # {CARPETA} es pot fer servir dins del fitxer per referir-se a la carpeta de JARVIS
        contingut = FITXER.read_text(encoding="utf-8").replace("{CARPETA}", str(CARPETA).replace("\\", "/"))
        dades = json.loads(contingut)
        servidors = {}
        # Format de JARVIS
        for nom, s in dades.get("servidors", {}).items():
            if s.get("activat", True):
                servidors[nom] = s
        # Format estàndard (el dels README de GitHub): tots activats
        for nom, s in dades.get("mcpServers", {}).items():
            if not s.get("disabled"):
                servidors[nom] = {"ordre": s.get("command"), "arguments": s.get("args", []),
                                  "entorn": s.get("env", {}), "url": s.get("url"),
                                  "capcaleres": s.get("headers", {}), "confirmar": "escriptura"}
        return servidors

    async def iniciar(self):
        """Arrenca tots els servidors activats i n'apunta les eines al registre."""
        from mcp import ClientSession
        for nom, s in self.configuracio().items():
            try:
                if s.get("url"):
                    from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
                    client = create_mcp_http_client(headers=s.get("capcaleres") or None)
                    fluxos = await self.pila.enter_async_context(
                        streamable_http_client(s["url"], http_client=client))
                else:
                    from mcp import StdioServerParameters
                    from mcp.client.stdio import stdio_client
                    ordre = s["ordre"]
                    if shutil.which(ordre) is None:
                        raise FileNotFoundError(f"no trobo el programa «{ordre}» (cal instal·lar-lo)")
                    parametres = StdioServerParameters(
                        command=ordre, args=s.get("arguments", []),
                        env={**os.environ, **s.get("entorn", {})})
                    registre = open(FITXER_REGISTRE, "a", encoding="utf-8")
                    fluxos = await self.pila.enter_async_context(stdio_client(parametres, errlog=registre))
                lectura, escriptura = fluxos[0], fluxos[1]
                sessio = await self.pila.enter_async_context(
                    ClientSession(lectura, escriptura, read_timeout_seconds=120))
                await sessio.initialize()
                eines = []
                cursor = None
                while True:
                    from mcp import types
                    r = await sessio.list_tools(params=types.PaginatedRequestParams(cursor=cursor) if cursor else None)
                    eines += r.tools
                    cursor = getattr(r, "next_cursor", None)
                    if not cursor:
                        break
                self.sessions[nom] = sessio
                for e in eines:
                    self._registrar(nom, s, e)
                PLUGINS[f"mcp:{nom}"] = f"{len(eines)} eines (MCP)"
                self.missatge("sys", f"MCP «{nom}» connectat: {len(eines)} eines.")
            except Exception as err:
                PLUGINS[f"mcp:{nom}"] = f"ERROR: {err}"
                self.missatge("err", f"No s'ha pogut connectar el servidor MCP «{nom}»: {err}")

    def _registrar(self, servidor, conf, eina_mcp):
        confirmar = conf.get("confirmar", "escriptura")
        nomes_lectura = bool(eina_mcp.annotations and eina_mcp.annotations.read_only_hint)
        if eina_mcp.name in conf.get("segures", []):
            perillosa = False
        elif eina_mcp.name in conf.get("perilloses", []):
            perillosa = True
        elif confirmar == "cap":
            perillosa = False
        elif confirmar == "totes":
            perillosa = True
        else:
            perillosa = not nomes_lectura
        esquema = convertir_esquema(eina_mcp.input_schema or {"type": "object"})
        nom_jarvis = _nom_valid(f"{servidor}_{eina_mcp.name}")

        async def cridar(**arguments):
            return await self.cridar(servidor, eina_mcp.name, arguments)

        registrar(Eina(
            nom=nom_jarvis,
            descripcio=f"[{servidor}] {(eina_mcp.description or eina_mcp.title or eina_mcp.name)[:900]}",
            funcio=cridar,
            parametres=esquema.get("properties", {}) if esquema["type"] == "OBJECT" else {},
            requerits=esquema.get("required", []),
            perillosa=perillosa,
            resum=lambda a, s=servidor, n=eina_mcp.name: f"{s} → {n}\n{json.dumps(a, ensure_ascii=False)[:600]}",
            plugin=f"mcp:{servidor}",
            asincrona=True,
        ))

    async def cridar(self, servidor, nom, arguments):
        sessio = self.sessions[servidor]
        # Els objectes "lliures" els hem demanat com a text JSON: els tornem a convertir
        for clau, valor in list(arguments.items()):
            if isinstance(valor, str) and valor[:1] in "{[":
                try:
                    arguments[clau] = json.loads(valor)
                except ValueError:
                    pass
        r = await sessio.call_tool(nom, arguments)
        textos, imatge = [], None
        for c in getattr(r, "content", []) or []:
            if getattr(c, "type", "") == "text":
                textos.append(c.text)
            elif getattr(c, "type", "") == "image" and imatge is None:
                imatge = _a_jpeg(c.data)
        if not textos and getattr(r, "structured_content", None):
            textos.append(json.dumps(r.structured_content, ensure_ascii=False))
        sortida = "\n".join(textos)[:8000] or "Fet."
        if getattr(r, "is_error", False):
            sortida = "Error: " + sortida
        return AmbImatge(sortida, imatge) if imatge else sortida

    async def tancar(self):
        await self.pila.aclose()


def _a_jpeg(base64_dades):
    import base64
    from PIL import Image
    img = Image.open(io.BytesIO(base64.b64decode(base64_dades)))
    img.thumbnail((1280, 1280))
    sortida = io.BytesIO()
    img.convert("RGB").save(sortida, "JPEG", quality=70)
    return sortida.getvalue()
