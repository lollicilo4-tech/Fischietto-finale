"""Genera il sito statico nella cartella docs/ (turno.json, storico.json, classifica.json, index.html).

Lo lancia GitHub Actions due volte al giorno; si può provare anche in locale:
    py generate.py
Le chiavi vengono lette da .env (in locale) o dai Secrets di GitHub (online).
Se qualcosa va storto non tocca i file già pubblicati.
"""
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from app import pipeline  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "docs"


async def main() -> int:
    try:
        turno = await pipeline.build_turno()
    except RuntimeError as exc:  # per esempio pausa per le nazionali: nessuna partita in programma
        print(f"Nessun aggiornamento: {exc}")
        return 0

    if turno["demo"] and os.getenv("CI"):
        print("Errore: manca FOOTBALL_DATA_KEY nei Secrets, non pubblico i dati di esempio.")
        return 1
    if turno.get("ai_error"):
        print(f"Attenzione: Claude non ha risposto ({turno['ai_error']}). Pubblico l'analisi a regole.")

    turno.pop("ai_error", None)  # i dettagli tecnici dell'errore non vanno nel file pubblico
    storico = await pipeline.build_storico()
    classifica = await pipeline.build_classifica()

    OUT.mkdir(exist_ok=True)
    (OUT / ".nojekyll").touch()  # GitHub Pages: servi i file così come sono
    for name, payload in (("turno.json", turno), ("storico.json", storico), ("classifica.json", classifica)):
        (OUT / name).write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    html = html.replace("/api/turno", "turno.json").replace("/api/storico", "storico.json")
    html = html.replace("/api/classifica", "classifica.json")
    (OUT / "index.html").write_text(html, encoding="utf-8")
    for f in (ROOT / "static").iterdir():  # icone, manifest e service worker per l'installazione su telefono
        if f.is_file() and f.name != "index.html":
            shutil.copy2(f, OUT / f.name)

    print(f"Sito aggiornato in {OUT}: {len(turno['matches'])} partite, "
          f"analisi {'Claude' if turno['ai'] else 'a regole'}.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
