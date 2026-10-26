# reconeixement.py
# Entén el «sí» o el «no» de les confirmacions amb el reconeixement de veu de
# Windows (sense Internet i en menys d'un segon).
#
# Fa servir System.Speech (el reconeixedor en castellano que porta Windows) des
# d'un procés de PowerShell que queda obert: li passem el camí d'un fitxer WAV i
# ens torna el que hi ha entès. Té dues "gramàtiques":
#   - "sino": només unes quantes frases (sí, hazlo, vale, no, cancela...);
#   - "dictat": qualsevol altra cosa. Serveix perquè una frase llarga com
#     «si no, espera» no s'entengui com un «sí» per error.

import base64
import subprocess
import threading

FRASES = ["sí", "sí hazlo", "hazlo", "vale", "adelante", "confirmo", "de acuerdo", "claro",
          "sí claro", "no", "no lo hagas", "cancela", "para", "no gracias"]

GUIO = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.Encoding]::UTF8
[Console]::OutputEncoding = [Text.Encoding]::UTF8
try {
    Add-Type -AssemblyName System.Speech
    $cultura = New-Object System.Globalization.CultureInfo('es-ES')
    $motor = New-Object System.Speech.Recognition.SpeechRecognitionEngine($cultura)
    $frases = New-Object System.Speech.Recognition.Choices
    $frases.Add([string[]]@(FRASES))
    $gb = New-Object System.Speech.Recognition.GrammarBuilder($frases)
    $gb.Culture = $cultura
    $g = New-Object System.Speech.Recognition.Grammar($gb); $g.Name = 'sino'
    $motor.LoadGrammar($g)
    $d = New-Object System.Speech.Recognition.DictationGrammar; $d.Name = 'dictat'
    $motor.LoadGrammar($d)
} catch { [Console]::Out.WriteLine("ERROR $_"); exit }
[Console]::Out.WriteLine('LLEST')
while (($ruta = [Console]::In.ReadLine()) -ne $null) {
    $trossos = @()
    try {
        $motor.SetInputToWaveFile($ruta)
        for ($i = 0; $i -lt 10; $i++) {
            try { $r = $motor.Recognize() } catch { break }      # final de l'àudio
            if ($r -ne $null) { $trossos += "$($r.Grammar.Name)`t$($r.Confidence)`t$($r.Text)" }
        }
        $motor.SetInputToNull()
    } catch {}
    [Console]::Out.WriteLine(($trossos -join '|'))
    [Console]::Out.Flush()
}
""".replace("FRASES", ", ".join(f"'{f}'" for f in FRASES))


class ReconeixedorLocal:
    def __init__(self):
        self.proces = None
        self.bloqueig = threading.Lock()
        self.no_disponible = False

    def _engegar(self):
        ordre = base64.b64encode(GUIO.encode("utf-16-le")).decode()
        self.proces = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", ordre],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        linia = self.proces.stdout.readline().strip()
        if linia != "LLEST":
            self.tancar()
            self.no_disponible = True
            raise RuntimeError(linia or "el reconeixement de veu de Windows no ha arrencat")

    def preparar(self):
        """Engega el reconeixedor per endavant (la primera vegada tarda un segon)."""
        with self.bloqueig:
            if not self.no_disponible and (self.proces is None or self.proces.poll() is not None):
                self._engegar()

    def reconeixer(self, ruta_wav):
        """Torna (text, segur). 'segur' vol dir que tot el que s'ha sentit són frases de la
        llista (sí, no, vale...) i el reconeixedor n'està prou convençut."""
        if self.no_disponible:
            return "", False
        with self.bloqueig:
            if self.proces is None or self.proces.poll() is not None:
                self._engegar()
            self.proces.stdin.write(str(ruta_wav) + "\n")
            self.proces.stdin.flush()
            linia = self.proces.stdout.readline().strip()
        textos, segur = [], True
        for tros in filter(None, linia.split("|")):
            gramatica, confianca, text = tros.split("\t", 2)
            confianca = float(confianca.replace(",", "."))
            if gramatica == "dictat" and confianca < 0.3:
                continue                   # restes de soroll
            textos.append(text)
            if gramatica != "sino" or confianca < 0.6:
                segur = False
        return " ".join(textos), segur and bool(textos)

    def tancar(self):
        if self.proces is not None:
            self.proces.kill()
            self.proces = None
