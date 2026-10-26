# JARVIS 2 — assistent de veu amb plugins

Assistent personal de veu per a Windows, inspirat en el JARVIS d'Iron Man, fet amb
PyQt6 i Gemini Live.

Li pots parlar o escriure, i a més de conversar pot **fer coses a l'ordinador**:
gestionar l'horari i els recordatoris, buscar i organitzar fitxers, controlar
finestres i programes, mirar la pantalla, posar música, dir el temps, treballar
amb Gmail, Google Calendar i Drive, i connectar-se a qualsevol servidor **MCP**
de GitHub.

## Com s'engega

**Opció ràpida:** baixa **`JARVIS2.exe`** de la secció *Releases* i fes-hi doble clic
(porta Python i totes les biblioteques a dins). Fa servir els fitxers de la mateixa carpeta: `config.json`,
`agenda.json`, `mcp_servers.json`, `google_credencials.json`... Els plugins nous que
posis a la carpeta `plugins/` del costat també es carreguen. Si canvies el codi dels
plugins que ja hi ha, cal tornar a crear l'.exe (o fer servir `py main.py`).

**Amb el codi font:**

1. **Python 3.11 o més nou**.
2. `py -m pip install -r requirements.txt`
3. Clau API de Gemini a <https://aistudio.google.com/apikey> (la demana la primera vegada).
4. `py main.py`
5. Opcional: connectar Google seguint **GUIA-GOOGLE.md**.

> No comparteixis mai `config.json`, `google_credencials.json` ni `google_token.json`.

## Què li pots demanar

| Plugin | Exemples |
|---|---|
| **agenda** | «Afegeix al meu horari mates els dilluns i dimecres a les 9» · «Què tinc demà?» · «Recorda'm d'aquí 20 minuts que tregui la pizza» · «Apunta't que he d'entregar el treball de física divendres» |
| **fitxers** | «Busca els apunts d'història» · «Resumeix-me el PDF de les Baixades» · «Fes una carpeta Física a l'Escriptori i mou-hi els apunts» · «Què ocupa més a les Baixades?» |
| **ordinador** | «Mira la meva pantalla i explica'm l'error» · «Porta el Word al davant i escriu…» · «Pausa la música» · «Obre la configuració del bluetooth» · «Apaga l'ordinador d'aquí una hora» · «Quina IP tinc?» |
| **web_i_apps** | «Quin temps farà demà a Girona?» · «Notícies de la Fórmula 1» · «Posa a YouTube lofi per estudiar» · «Busca Bad Bunny a Spotify» · «Prepara un WhatsApp al 600…» |
| **google** | «Tinc correus nous?» · «Respon-li que sí» · «Què tinc al Google Calendar?» · «Busca al Drive l'horari» · «Afegeix a Google Tasks…» |
| **basiques** | Obrir aplicacions i webs, volum, estat del sistema, data i hora, notes |
| **càmera** | «Mostra'm el que veus» |

A més té la **cerca de Google** integrada per a preguntes d'actualitat.

## Seguretat: les accions perilloses es confirmen

Les eines que poden fer mal (esborrar fitxers o esdeveniments, moure fitxers,
sobreescriure, enviar correus i WhatsApps, convidar gent, tancar programes,
prémer tecles, apagar l'ordinador, executar PowerShell i les eines MCP que
escriuen) **no s'executen fins que l'usuari prem «Sí, fes-ho»** en una finestra
que explica exactament què es farà, **o diu «sí» en veu alta**. Si no es respon en
90 segons, és un no.

- Per veu, mentre la finestra és oberta el micròfon no va a Gemini: la frase es
  transcriu a part i és el programa qui decideix. Qualsevol «no» guanya, i un «sí»
  només compta en frases curtes. Es pot desactivar amb `"confirmar_per_veu": false`.

- Esborrar envia a la **Paperera** (es pot recuperar).
- Es pot desactivar a `config.json` amb `"confirmar_perilloses": false` (no és recomanable).

## Els plugins

Cada fitxer de la carpeta `plugins/` és un plugin i es carrega sol en obrir
JARVIS. Per desactivar-ne un, posa'l a `config.json`:
`"plugins_desactivats": ["web_i_apps"]`.

### Com fer un plugin nou

Crea `plugins/dau.py`:

```python
import random
from eines import eina, enter

DESCRIPCIO = "Jocs d'atzar"

@eina("Tira un o més daus de sis cares.",
      parametres={"quants": enter("Quants daus (per defecte 1)")})
def tirar_daus(quants=1):
    return "Ha sortit: " + ", ".join(str(random.randint(1, 6)) for _ in range(quants))
```

Torna a obrir JARVIS i ja pots dir «tira dos daus». Gemini llegeix la descripció
per decidir quan l'ha de fer servir. Opcions de `@eina`:

- `parametres`: amb `text()`, `enter()`, `decimal()`, `boolea()`, `opcions(desc, [valors])`, `llista()`.
- `perillosa=True` (o una funció que rep els arguments) perquè demani confirmació.
- `resum=lambda a: "..."`: la frase que surt a la finestra de confirmació.
- Per tornar una imatge perquè Gemini la vegi: `return AmbImatge(text, jpeg)`.
- Si el plugin té una funció `iniciar(context)`, es crida en carregar-lo.
  `context.avisar("text")` fa que JARVIS ho digui en veu alta (així funcionen els recordatoris).

## Servidors MCP (plugins de GitHub)

**MCP** (Model Context Protocol) és l'estàndard per connectar assistents d'IA amb
eines. A GitHub n'hi ha milers. JARVIS els connecta a través de `mcp_pont.py` i
els configura a **`mcp_servers.json`**. Ja hi ha preparats (desactivats):

| Servidor | Què fa | Cal |
|---|---|---|
| `windows` — [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) | Fa clic, escriu i llegeix qualsevol finestra | `uv` |
| `google_workspace` — [google_workspace_mcp](https://github.com/taylorwilsdon/google_workspace_mcp) | Docs, Sheets, Slides i Forms | `uv` + `google_credencials.json` |
| `navegador` — [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Navega per webs, omple formularis | Node.js |
| `notion` — [Notion MCP](https://github.com/makenotion/notion-mcp-server) | Pàgines i bases de dades de Notion | Node.js + token |

Per activar-ne un, posa `"activat": true`. També pots enganxar-hi el bloc
`"mcpServers"` que surt al README de qualsevol servidor MCP. Els errors dels
servidors es desen a `mcp_registre.log`.

Les eines MCP que només llegeixen no demanen permís; la resta, sí (es pot
canviar amb `confirmar`, `segures` i `perilloses`).

## Fitxers

| Fitxer | Què fa |
|---|---|
| `main.py` | Punt d'entrada. |
| `config.py` | Llegeix i desa `config.json`. |
| `assistent.py` | Connexió amb Gemini Live, micròfon, altaveu, execució d'eines i confirmacions. |
| `eines.py` | El registre d'eines, el decorador `@eina` i la càrrega de plugins. |
| `reconeixement.py` | Entén el «sí» o el «no» de les confirmacions amb el reconeixement de veu de Windows. |
| `mcp_pont.py` | El pont amb els servidors MCP (i la conversió d'esquemes per a Gemini). |
| `interficie.py` | La finestra: reactor, monitor, agenda d'avui, registre i confirmacions. |
| `camera.py` | La càmera web. |
| `plugins/*.py` | Els plugins. |
| `agenda.json`, `notes.txt` | Les dades de l'agenda i les notes (es creen soles). |

## Detall tècnic important

Gemini Live **s'inventa els noms dels paràmetres** si se li passa l'esquema en
format JSON Schema (`parameters_json_schema`), però els respecta amb el seu format
propi (`"type": "STRING"`, `"OBJECT"`...). Ho vam comprovar amb una prova: per
això `eines.py` fa servir aquest format i `mcp_pont.py` converteix els esquemes
dels servidors MCP.

## Limitacions

- Necessita Internet i una clau de Gemini (la versió gratuïta té un límit diari).
- Les eines de control de Windows només funcionen a Windows.
- Els recordatoris només sonen si JARVIS està obert (si s'obre tard, avisa dels pendents).
- WhatsApp i Spotify s'obren amb els seus enllaços: Spotify obre la cerca, però cal prémer play.
- Gemini es pot equivocar: per això les accions perilloses sempre es confirmen.

## Crèdits

- Idea inspirada en el projecte JARVIS de FatihMakes. El codi és nou.
- Fet amb l'ajuda de Claude (Anthropic).
- Biblioteques: PyQt6, google-genai, sounddevice, numpy, psutil, OpenCV, requests,
  Pillow, PyAutoGUI, PyGetWindow, pyperclip, Send2Trash, python-docx, pypdf,
  google-api-python-client i mcp. Temps: Open-Meteo. Notícies: Google Notícies.
