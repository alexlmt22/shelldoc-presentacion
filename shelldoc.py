import argparse
import os
import signal
import subprocess
import sys
import threading
import time

from generador_qmd import generar_qmd
from parser_script import leer_sesion

CARPETA = os.path.dirname(os.path.abspath(__file__)) 
ARCHIVO_QMD = "presentacion.qmd"
ARCHIVO_HTML = "presentacion.html"

PAUSA = 2

sem_render = threading.Semaphore(0)    
sem_servidor = threading.Semaphore(0)  
sem_publicar = threading.Semaphore(0)

hay_error = False              
mensaje_error = ""             
lock_error = threading.Lock()  
lock_print = threading.Lock()  
detener = threading.Event()    

def log(mensaje):
    """Imprime un mensaje con la hora y el nombre del hilo que lo escribe."""
    hora = time.strftime("%H:%M:%S")
    nombre = threading.current_thread().name
    with lock_print: 
        print(f"[{hora}] [{nombre}] {mensaje}", flush=True)


def marcar_error(mensaje):
    global hay_error, mensaje_error
    with lock_error:
        if not hay_error:
            hay_error = True
            mensaje_error = threading.current_thread().name + ": " + mensaje
    log("ERROR: " + mensaje)


def hubo_error():
    with lock_error:
        return hay_error


def ejecutar(comando, tiempo_maximo=300):
    try:
        resultado = subprocess.run(
            comando,
            cwd=CARPETA,               
            stdin=subprocess.DEVNULL,  
            capture_output=True,       
            text=True,
            errors="replace",
            timeout=tiempo_maximo,
        )
    except FileNotFoundError:
        raise Exception(
            f"no encontré el programa '{comando[0]}'. ¿Está instalado? "
            f"(prueba con: {comando[0]} --version)"
        )
    except subprocess.TimeoutExpired:
        raise Exception(f"'{' '.join(comando)}' tardó más de {tiempo_maximo} segundos")
    texto = (resultado.stdout + resultado.stderr).strip()
    return resultado.returncode, texto


def detener_proceso(proceso):
    try:
        os.killpg(proceso.pid, signal.SIGTERM)  
        proceso.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(proceso.pid, signal.SIGKILL)  
        proceso.wait()
    except ProcessLookupError:
        pass  


def hilo1_transformador(args):
    log("Inicio. No dependo de ningún otro hilo, empiezo a leer la sesión.")
    try:
        if args.simular_error == "hilo1":
            raise Exception("error simulado en el Hilo 1 (prueba de interbloqueo)")

        comandos = leer_sesion(args.sesion)
        log(f"Sesión leída y limpiada: {len(comandos)} comandos encontrados.")
        if len(comandos) == 0:
            raise Exception("no encontré ningún comando en " + args.sesion)

        time.sleep(PAUSA)  # solo para que se vea la espera de los otros hilos

        texto_qmd = generar_qmd(comandos)
        with open(os.path.join(CARPETA, ARCHIVO_QMD), "w", encoding="utf-8") as archivo:
            archivo.write(texto_qmd)
        log(f"RESULTADO: {ARCHIVO_QMD} generado ({len(comandos)} diapositivas).")
    except Exception as e:
        marcar_error(str(e))
    finally:
        log("signal(sem_render) -> aviso al Hilo 2.")
        sem_render.release()

def hilo2_renderizador(args):
    log("Inicio. Antes de renderizar tengo que esperar al Hilo 1.")
    log("wait(sem_render) -> me bloqueo hasta que el Hilo 1 termine.")
    sem_render.acquire()  
    log("wait(sem_render) superado: el Hilo 1 ya terminó.")
    try:
        if hubo_error():
            log("El Hilo 1 falló, así que no renderizo nada.")
            return  

        if args.simular_error == "hilo2":
            raise Exception("error simulado en el Hilo 2 (prueba de interbloqueo)")

        log(f"Ejecutando: quarto render {ARCHIVO_QMD}")
        codigo, texto = ejecutar(["quarto", "render", ARCHIVO_QMD])
        if codigo != 0:
            raise Exception(f"quarto render falló (código {codigo}): {texto}")

        ruta_html = os.path.join(CARPETA, ARCHIVO_HTML)
        if not os.path.isfile(ruta_html) or os.path.getsize(ruta_html) == 0:
            raise Exception(f"quarto terminó pero no se generó {ARCHIVO_HTML}")
        if texto:
            log("quarto dice: " + texto.splitlines()[-1])
        log(f"RESULTADO: {ARCHIVO_HTML} generado correctamente.")
    except Exception as e:
        marcar_error(str(e))
    finally:
        if args.publicar:
            log("signal(sem_publicar) -> aviso al Hilo 4.")
            sem_publicar.release()
        else:
            log("signal(sem_servidor) -> aviso al Hilo 3.")
            sem_servidor.release()


def hilo3_servidor(args):
    log("Inicio. Necesito que exista una presentación válida para abrir el servidor.")
    log("wait(sem_servidor) -> me bloqueo hasta que me avisen.")
    sem_servidor.acquire() 
    log("wait(sem_servidor) superado.")

    if hubo_error() or detener.is_set():
        log("Hubo un error (o cancelaron) en una etapa anterior: no inicio el servidor.")
        return

    comando = ["quarto", "preview", ARCHIVO_QMD,"--host","0.0.0.0", "--port", str(args.puerto)]
    if args.sin_navegador:
        comando.append("--no-browser")

    log("Iniciando: " + " ".join(comando))
    try:
        proceso = subprocess.Popen(
            comando, cwd=CARPETA, stdin=subprocess.DEVNULL, start_new_session=True
        )
    except FileNotFoundError:
        marcar_error("no encontré el programa 'quarto'. ¿Está instalado?")
        return
    except Exception as e:
        marcar_error(str(e))
        return

    log(f"RESULTADO: servidor en marcha (pid {proceso.pid}) -> http://localhost:{args.puerto}")
    log("Presiona Ctrl+C para detener la aplicación.")

    while not detener.is_set() and proceso.poll() is None:
        detener.wait(0.5)

    if proceso.poll() is None:
        log("Ctrl+C recibido: cerrando quarto preview...")
        detener_proceso(proceso)
        log("RESULTADO: servidor detenido de forma controlada.")
    else:
        marcar_error(f"quarto preview se cerró solo (código {proceso.returncode}). "
                     f"¿El puerto {args.puerto} está ocupado?")


def hilo4_publicador(args):
    log("Inicio (funcionalidad extra). Publico solo cuando el Hilo 2 haya renderizado bien.")
    log("wait(sem_publicar) -> me bloqueo hasta que me avisen.")
    sem_publicar.acquire()  
    log("wait(sem_publicar) superado.")
    try:
        if hubo_error():
            log("Hubo un error en una etapa anterior: cancelo la publicación.")
            return

        comando = ["quarto", "publish", "gh-pages", ARCHIVO_QMD, "--no-prompt", "--no-browser"]
        if args.simular_publicacion:
            log("SIMULACIÓN: aquí se ejecutaría -> " + " ".join(comando))
            time.sleep(2)
            log("RESULTADO: publicación simulada (no se subió nada a internet).")
            return

        log("Publicando en GitHub Pages: " + " ".join(comando))
        codigo, texto = ejecutar(comando, tiempo_maximo=300)
        if codigo != 0:
            raise Exception(f"quarto publish falló (código {codigo}): {texto}")
        for linea in texto.splitlines()[-2:]:
            log("quarto dice: " + linea)
        log("RESULTADO: presentación publicada en GitHub Pages.")
    except Exception as e:
        marcar_error(str(e))
    finally:
        log("signal(sem_servidor) -> aviso al Hilo 3.")
        sem_servidor.release()

def manejar_ctrl_c(numero_senal, frame):
    """Se ejecuta cuando el usuario presiona Ctrl+C (o llega SIGTERM)."""
    log("Señal de parada recibida. Aviso a los hilos para que terminen.")
    detener.set()


def leer_argumentos():
    parser = argparse.ArgumentParser(
        description="ShellDoc Web: convierte una sesión de terminal Linux (script) "
                    "en una presentación de Quarto usando hilos y semáforos."
    )
    parser.add_argument("--sesion", default=os.path.join(CARPETA, "session.txt"),
                        help="archivo grabado con `script` (por defecto: session.txt)")
    parser.add_argument("--puerto", type=int, default=4200,
                        help="puerto del servidor web (por defecto: 4200)")
    parser.add_argument("--sin-navegador", action="store_true",
                        help="no abrir el navegador automáticamente")
    parser.add_argument("--publicar", action="store_true",
                        help="EXTRA: activa el Hilo 4 que publica en GitHub Pages")
    parser.add_argument("--simular-publicacion", action="store_true",
                        help="EXTRA: el Hilo 4 solo simula la publicación (no sube nada)")
    parser.add_argument("--simular-error", choices=["hilo1", "hilo2"],
                        help="provoca un error a propósito para probar que no hay interbloqueo")
    return parser.parse_args()


def main():
    args = leer_argumentos()
    if args.simular_publicacion:
        args.publicar = True  

    threading.current_thread().name = "Principal"
    signal.signal(signal.SIGINT, manejar_ctrl_c)   
    signal.signal(signal.SIGTERM, manejar_ctrl_c)  

    print("=" * 62)
    print(" ShellDoc Web - hilos y semáforos")
    print("=" * 62)
    log("Semáforos creados con valor inicial 0: sem_render, sem_servidor, sem_publicar.")

    hilos = [
        threading.Thread(target=hilo1_transformador, args=(args,), name="Hilo 1 - Transformador"),
        threading.Thread(target=hilo2_renderizador, args=(args,), name="Hilo 2 - Renderizador"),
        threading.Thread(target=hilo3_servidor, args=(args,), name="Hilo 3 - Servidor"),
    ]
    if args.publicar:
        hilos.append(
            threading.Thread(target=hilo4_publicador, args=(args,), name="Hilo 4 - Publicador")
        )

    log(f"Lanzando {len(hilos)} hilos...")
    for hilo in hilos:
        hilo.start()

    while any(hilo.is_alive() for hilo in hilos):
        time.sleep(0.3)

    print()
    if hubo_error():
        print(f"[RESUMEN] El programa terminó con error -> {mensaje_error}")
        return 1
    log("RESUMEN: todos los hilos terminaron de forma controlada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
