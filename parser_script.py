import re

RE_TITULO = re.compile(r"\x1b\][^\x07\x1b]*(\x07|\x1b\\)")

RE_CSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")

RE_ESC_OTROS = re.compile(r"\x1b[()][A-Za-z0-9]|\x1b[=>@-Z\\-_]")

RE_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

RE_PROMPT = re.compile(r"^(\(.*?\)\s*)?[\w.-]+@[\w.-]+:[^$#]*[$#] ?(.*)$")


def limpiar_texto(texto):
    """Quita los códigos de escape y devuelve una lista de líneas limpias."""
    texto = RE_TITULO.sub("", texto)
    texto = RE_CSI.sub("", texto)
    texto = RE_ESC_OTROS.sub("", texto)
    texto = texto.replace("\r\n", "\n")

    lineas = []
    for linea in texto.split("\n"):
        if "\r" in linea:
            trozos = [t for t in linea.split("\r") if t != ""]
            linea = trozos[-1] if trozos else ""
        resultado = ""
        for caracter in linea:
            if caracter == "\b":
                resultado = resultado[:-1]
            else:
                resultado += caracter
        lineas.append(RE_CONTROL.sub("", resultado))
    return lineas

def extraer_comandos(texto):
    """Recibe el texto completo de la sesión y devuelve la lista de comandos."""
    lineas = limpiar_texto(texto)
    bloques = []  
    for linea in lineas:
        if linea.startswith("Script started") or linea.startswith("Script done"):
            continue

        coincide = RE_PROMPT.match(linea)
        if coincide:
            bloques.append([coincide.group(2).strip(), []])
        elif len(bloques) > 0:
            bloques[-1][1].append(linea)

    comandos = []
    for comando, salida in bloques:
        if comando == "" or comando in ("exit", "logout"):
            continue
        while len(salida) > 0 and salida[-1].strip() == "":
            salida.pop()
        comandos.append(
            {
                "numero": len(comandos) + 1,
                "comando": comando,
                "salida": "\n".join(salida),
            }
        )
    return comandos


def leer_sesion(ruta):
    """Abre el archivo session.txt y devuelve la lista de comandos."""
    with open(ruta, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        texto = f.read()
    return extraer_comandos(texto)