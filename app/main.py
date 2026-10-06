"""Server locale: serve la pagina e le due API. Per la pubblicazione online si usa generate.py."""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from . import pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="Fischietto finale")


@app.get("/api/turno")
async def turno():
    try:
        return await pipeline.build_turno()
    except Exception as exc:
        return JSONResponse({"error": f"Impossibile leggere i dati: {exc}"}, status_code=502)


@app.get("/api/storico")
async def storico():
    return await pipeline.build_storico()


@app.get("/api/classifica")
async def classifica():
    try:
        return await pipeline.build_classifica()
    except Exception as exc:
        return JSONResponse({"error": f"Impossibile leggere i dati: {exc}"}, status_code=502)


# Pagina, icone, manifest: tutto ciò che sta in static/ è servito dalla radice (dopo le API)
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")
