"""Actualiza los datos de Mi Radar Musical para el despliegue diario de GitHub Actions."""
import shutil
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
APP = RAIZ / "app"


def ejecutar(*argumentos):
    print("\n$ " + " ".join(str(x) for x in argumentos), flush=True)
    subprocess.run(argumentos, cwd=RAIZ, check=True)


def main():
    ejecutar(sys.executable, str(APP / "detector.py"), "--all")
    ejecutar(sys.executable, str(APP / "preparar_portada.py"))
    shutil.copy2(RAIZ / "portada.json", APP / "portada.json")

    # Actualiza también las listas musicales para que haya datos disponibles
    # desde la primera visita, sin depender de que el usuario pulse un botón.
    sys.path.insert(0, str(APP))
    from listas_musicales import actualizar

    for tipo in ("los40", "canal-fiesta", "youtube"):
        resultado = actualizar(tipo)
        if resultado.get("error"):
            print(
                f"AVISO: no se pudo actualizar {tipo}: "
                f"{resultado.get('mensaje', 'error desconocido')}",
                flush=True,
            )
        else:
            print(
                f"Correcto: {tipo}: {len(resultado.get('canciones', []))} canciones.",
                flush=True,
            )


if __name__ == "__main__":
    main()
