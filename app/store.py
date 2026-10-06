"""Storico: ogni pronostico viene salvato prima della partita e mai riscritto,
poi confrontato con il risultato reale. È l'unico modo per sapere se il modello funziona."""
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "predictions.db"


def _conn() -> sqlite3.Connection:
    DB.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(DB)
    c.execute("""CREATE TABLE IF NOT EXISTS predictions (
        match_id TEXT PRIMARY KEY, home TEXT, away TEXT, kickoff TEXT,
        p1 REAL, px REAL, p2 REAL, pick TEXT, pick_p REAL, created TEXT DEFAULT CURRENT_TIMESTAMP)""")
    return c


def save(match_id: str, home: str, away: str, kickoff: str, p1: float, px: float, p2: float) -> None:
    pick, pick_p = max((("1", p1), ("X", px), ("2", p2)), key=lambda x: x[1])
    with _conn() as c:  # INSERT OR IGNORE: il primo pronostico resta quello valido
        c.execute("INSERT OR IGNORE INTO predictions (match_id, home, away, kickoff, p1, px, p2, pick, pick_p) "
                  "VALUES (?,?,?,?,?,?,?,?,?)", (match_id, home, away, kickoff, p1, px, p2, pick, pick_p))


def history(finished: list[dict]) -> dict:
    results = {m["id"]: m for m in finished}
    items = []
    with _conn() as c:
        rows = c.execute("SELECT match_id, home, away, kickoff, pick, pick_p FROM predictions "
                         "ORDER BY kickoff DESC").fetchall()
    for mid, home, away, kickoff, pick, p in rows:
        m = results.get(mid)
        if not m:
            continue
        actual = "1" if m["hg"] > m["ag"] else "X" if m["hg"] == m["ag"] else "2"
        items.append({"match": f"{home} – {away}", "pick": pick, "p": p,
                      "score": f"{m['hg']}-{m['ag']}", "ok": pick == actual})
    n = len(items)
    hit = sum(1 for i in items if i["ok"])
    return {"n": n, "hit": hit, "avg_p": (sum(i["p"] for i in items) / n) if n else None,
            "items": items[:30]}
