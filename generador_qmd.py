CARACTERES_ESPECIALES = "\\`*_{}[]<>#|$~^@&"
LARGO_TITULO = 50

def escapar_titulo(texto):
    resultado = ""
    for caracter in texto:
        if caracter in CARACTERES_ESPECIALES:
            resultado += "\\" + caracter
        else:
            resultado += caracter
    resultado = resultado.replace("--", "-\\-")
    return resultado

def hacer_titulo(comando):
    una_linea = " ".join(comando.split())
    if len(una_linea) > LARGO_TITULO:
        una_linea = una_linea[:LARGO_TITULO] + "..."
    return escapar_titulo(una_linea)

def calcular_cerca(texto):
    racha_maxima = 0
    racha_actual = 0
    for caracter in texto:
        if caracter == "`":
            racha_actual += 1
            racha_maxima = max(racha_maxima, racha_actual)
        else:
            racha_actual = 0
    return "`" * max(3, racha_maxima + 1)

def bloque_codigo(texto, lenguaje, nombre_archivo):
    cerca = calcular_cerca(texto)
    primera_linea = cerca + "{." + lenguaje + ' filename="' + nombre_archivo + '"}'
    return primera_linea + "\n" + texto + "\n" + cerca

def texto_lineas(salida):
    if salida == "":
        return "Este comando no produjo salida."
    cantidad = len(salida.split("\n"))
    if cantidad == 1:
        return "1 línea de salida conservada."
    return str(cantidad) + " líneas de salida conservadas."

def hacer_diapositiva(comando):
    titulo = hacer_titulo(comando["comando"])
    salida = comando["salida"] if comando["salida"] != "" else "(sin salida)"
 
    bloque_comando = bloque_codigo("$ " + comando["comando"], "bash", "terminal")
    bloque_salida = bloque_codigo(salida, "text", "session.txt")
 
    lineas = [
        "## Comando " + str(comando["numero"]) + ": " + titulo,
        "",
        ":::: {.columns}",
        "",
        '::: {.column width="48%"}',
        "[Comando]{.col-titulo}",
        "",
        bloque_comando,
        "",
        "[Comando registrado en la sesión Linux.]{.nota}",
        ":::",
        "",
        '::: {.column width="4%"}',  # columna vacía, solo para separar
        ":::",
        "",
        '::: {.column width="48%"}',
        "[Salida]{.col-titulo}",
        "",
        bloque_salida,
        "",
        "[" + texto_lineas(comando["salida"]) + "]{.nota}",
        ":::",
        "",
        "::::",
        "",
    ]
    return "\n".join(lineas)

def generar_qmd(comandos):
    cabecera = [
        "---",
        'title: "ShellDoc Web"',
        'subtitle: "Sesión de terminal Linux convertida en diapositivas"',
        "format:",
        "  revealjs:",
        "    theme: dark",
        "    slide-number: true",
        "    css: styles.css",
        "---",
        "",
    ]
 
    partes = ["\n".join(cabecera)]
    for comando in comandos:
        partes.append(hacer_diapositiva(comando))
    return "\n".join(partes)