"""Storico: ogni pronostico viene salvato prima della partita e mai riscritto,
poi confrontato con il risultato reale. È l'unico modo per sapere se il modello funziona.

Il file è un JSON semplice (data/predictions.json), così può essere salvato nel
repository e sopravvivere agli aggiornamenti automatici del sito.
"""
import json
import sqlite3
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
FILE = DATA / "predictions.json"
LEGACY_DB = DATA / "predictions.db"  # versione precedente, importata una sola volta


def _import_legacy() -> dict:
    out: dict = {}
    if not LEGACY_DB.exists():
        return out
    try:
        c = sqlite3.connect(LEGACY_DB)
        rows = c.execute("SELECT match_id, home, away, kickoff, p1, px, p2, pick, pick_p FROM predictions").fetchall()
        c.close()
    except sqlite3.Error:
        return out
    for mid, home, away, kickoff, p1, px, p2, pick, pick_p in rows:
        out[mid] = dict(home=home, away=away, kickoff=kickoff, p1=p1, px=px, p2=p2, pick=pick, pick_p=pick_p)
    return out


def _load() -> dict:
    if FILE.exists():
        return json.loads(FILE.read_text(encoding="utf-8"))  # se è corrotto meglio un errore che perdere lo storico
    legacy = _import_legacy()
    if legacy:
        _write(legacy)  # migrazione una tantum da predictions.db
    return legacy


def _write(d: dict) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(FILE)


def save(match_id: str, home: str, away: str, kickoff: str, p1: float, px: float, p2: float) -> None:
    d = _load()
    if match_id in d:  # il primo pronostico resta quello valido
        return
    pick, pick_p = max((("1", p1), ("X", px), ("2", p2)), key=lambda x: x[1])
    d[match_id] = dict(home=home, away=away, kickoff=kickoff, p1=p1, px=px, p2=p2, pick=pick, pick_p=pick_p)
    _write(d)


def history(finished: list[dict]) -> dict:
    results = {m["id"]: m for m in finished}
    items = []
    for mid, p in sorted(_load().items(), key=lambda kv: kv[1].get("kickoff") or "", reverse=True):
        m = results.get(mid)
        if not m:
            continue
        actual = "1" if m["hg"] > m["ag"] else "X" if m["hg"] == m["ag"] else "2"
        items.append({"match": f"{p['home']} – {p['away']}", "pick": p["pick"], "p": p["pick_p"],
                      "score": f"{m['hg']}-{m['ag']}", "ok": p["pick"] == actual})
    n = len(items)
    hit = sum(1 for i in items if i["ok"])
    return {"n": n, "hit": hit, "avg_p": (sum(i["p"] for i in items) / n) if n else None,
            "items": items[:30]}
