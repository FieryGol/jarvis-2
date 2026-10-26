# Connectar JARVIS amb Google (Calendar, Gmail, Drive, Tasks i Contactes)

Només cal fer-ho **una vegada**. Són uns 10 minuts. JARVIS mai veu la teva
contrasenya: Google li dona un permís que pots retirar quan vulguis.

## 1. Crear el projecte a Google Cloud

1. Entra a <https://console.cloud.google.com/> amb el teu **Gmail personal**.
2. A dalt de tot, fes clic al selector de projectes → **Projecte nou**.
   Nom: `JARVIS` → **Crea**. Assegura't que queda seleccionat.

## 2. Activar les API

Ves a **API i serveis → Biblioteca** i activa (botó **Activa**) aquestes cinc:

- Google Calendar API
- Gmail API
- Google Drive API
- Google Tasks API
- People API (és la dels contactes)

## 3. La pantalla de consentiment

1. **API i serveis → Pantalla de consentiment d'OAuth** (o **Google Auth Platform → Branding**).
2. Tipus d'usuari: **Extern** → Crea.
3. Nom de l'aplicació: `JARVIS`. Correu d'assistència i de contacte: el teu Gmail. Desa.
4. A **Públic** (o *Audience*) → **Usuaris de prova** → **Afegeix usuaris** → escriu el teu Gmail.
   (Mentre l'aplicació estigui "en proves", només la poden fer servir els usuaris de prova.)

## 4. Crear el client OAuth

1. **API i serveis → Credencials → Crea credencials → ID de client d'OAuth**.
2. Tipus d'aplicació: **Aplicació d'escriptori**. Nom: `JARVIS escriptori` → **Crea**.
3. A la finestra que surt, prem **Baixa el JSON**.
4. Canvia el nom del fitxer baixat per **`google_credencials.json`** i posa'l a la
   carpeta de JARVIS 2 (al costat de `main.py`, o de `JARVIS2.exe`).

## 5. Connectar

1. Obre JARVIS i digues-li: **«Connecta Google»**.
2. S'obrirà el navegador. Tria el teu compte.
3. Google avisarà que l'aplicació no està verificada (és normal: l'has creat tu).
   Prem **Continua** i marca tots els permisos.
4. Quan surti «JARVIS ja està connectat a Google», ja pots tancar la pestanya.
   Mentre ho fas pots continuar parlant amb JARVIS: quan acabis, et dirà amb quin
   compte s'ha connectat (o que no s'ha pogut, si passen 5 minuts o no dones permís).

Si surt **«Error 403: access_denied»**, és que el teu Gmail no és a la llista
d'usuaris de prova (pas 3.4). Afegeix-lo i torna-ho a provar.

Es crearà `google_token.json` a la carpeta. **No comparteixis ni aquest fitxer ni
`google_credencials.json`**: qui els tingui pot accedir al teu compte.

## 6. Que el permís no caduqui cada 7 dies

Mentre l'aplicació estigui **en proves**, Google fa caducar el permís als 7 dies i
cal tornar a dir «Connecta Google». Per evitar-ho, quan ja ho tinguis tot funcionant:

1. **Google Auth Platform → Públic** → **Publica l'aplicació** → Confirma.
2. Digues a JARVIS **«Connecta Google»** una vegada més (el permís antic encara és el de proves).

Continuarà sortint l'avís d'aplicació no verificada en connectar-te: és normal,
perquè només la fas servir tu.

## Què li pots demanar

- «Què tinc al Google Calendar aquesta setmana?»
- «Posa al calendari dinar amb l'avi dissabte a les 2»
- «Tinc correus nous?» · «Llegeix-me el correu del Joan» · «Respon-li que hi aniré»
- «Busca al Drive els apunts d'història i fes-me'n un resum»
- «Afegeix a Google Tasks comprar llibreta»
- «Quin és el correu de la Marta?»

Enviar correus, convidar gent a esdeveniments i esborrar-los demana sempre
confirmació a la finestra.

## Treure el permís

<https://myaccount.google.com/permissions> → **JARVIS** → **Suprimeix l'accés**.
Després esborra `google_token.json`.

## Docs, Sheets i Slides

El plugin `google.py` llegeix Documents, Fulls i Presentacions del Drive i crea
Documents nous. Per editar-los a fons pots activar el servidor MCP
`google_workspace` a `mcp_servers.json` (fa servir el mateix `google_credencials.json`).
