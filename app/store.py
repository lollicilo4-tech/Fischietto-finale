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


def save(match_id: str, home: str, away: str, kickoff: str, p1: float, px: float, p2: float,
         extra: dict | None = None) -> None:
    d = _load()
    if match_id in d:  # il primo pronostico resta quello valido
        return
    pick, pick_p = max((("1", p1), ("X", px), ("2", p2)), key=lambda x: x[1])
    d[match_id] = dict(home=home, away=away, kickoff=kickoff, p1=p1, px=px, p2=p2, pick=pick, pick_p=pick_p)
    if extra:  # altri mercati e gol attesi, per la scheda e per le metriche (assenti nei pronostici più vecchi)
        d[match_id].update(extra)
    _write(d)


def _outcome(m: dict) -> str:
    return "1" if m["hg"] > m["ag"] else "X" if m["hg"] == m["ag"] else "2"


def _joined(finished: list[dict]) -> list[tuple[str, dict, dict]]:
    results = {m["id"]: m for m in finished}
    rows = [(mid, p, results[mid]) for mid, p in _load().items() if mid in results]
    rows.sort(key=lambda r: r[1].get("kickoff") or "", reverse=True)
    return rows


def recent(finished: list[dict], limit: int = 9) -> list[dict]:
    """Ultime partite giocate che avevano un pronostico salvato, con il risultato vero."""
    out = []
    for mid, p, m in _joined(finished)[:limit]:
        actual = _outcome(m)
        item = {"id": mid, "home": p["home"], "away": p["away"], "kickoff": p.get("kickoff"),
                "prob": {"p1": p["p1"], "px": p["px"], "p2": p["p2"]},
                "pick": p["pick"], "pick_p": p["pick_p"], "hg": m["hg"], "ag": m["ag"],
                "actual": actual, "ok": p["pick"] == actual}
        if p.get("o25") is not None:
            item["ou"] = {"p": p["o25"], "ok": (m["hg"] + m["ag"] >= 3) == (p["o25"] >= 0.5)}
        if p.get("gg") is not None:
            item["gg"] = {"p": p["gg"], "ok": (m["hg"] > 0 and m["ag"] > 0) == (p["gg"] >= 0.5)}
        if p.get("top"):
            item["top"] = p["top"]
        out.append(item)
    return out


def history(finished: list[dict]) -> dict:
    rows = _joined(finished)
    items, brier, outcomes = [], [], []
    for mid, p, m in rows:
        actual = _outcome(m)
        outcomes.append(actual)
        brier.append(sum((q - (1.0 if k == actual else 0.0)) ** 2
                         for k, q in (("1", p["p1"]), ("X", p["px"]), ("2", p["p2"]))))
        items.append({"match": f"{p['home']} – {p['away']}", "pick": p["pick"], "p": p["pick_p"],
                      "score": f"{m['hg']}-{m['ag']}", "ok": p["pick"] == actual})
    n = len(items)
    out = {"n": n, "hit": sum(1 for i in items if i["ok"]),
           "avg_p": (sum(i["p"] for i in items) / n) if n else None, "items": items[:30]}
    if not n:
        return out

    # Metodo di riferimento: usare sempre le frequenze di 1, X, 2 dell'intero campionato
    tot = len(finished)
    base = {k: sum(1 for m in finished if _outcome(m) == k) / tot for k in ("1", "X", "2")}
    brier_base = sum(sum((base[k] - (1.0 if k == a else 0.0)) ** 2 for k in base) for a in outcomes) / n
    out["brier"] = sum(brier) / n
    out["brier_base"] = brier_base
    out["base_rates"] = {k: round(v, 3) for k, v in base.items()}

    # Calibrazione: quando dichiaro una certa probabilità, quanto spesso ci prendo davvero?
    buckets = []
    for lo, hi, label in ((0, 0.45, "sotto 45%"), (0.45, 0.55, "45-55%"), (0.55, 0.65, "55-65%"), (0.65, 1.01, "65% o più")):
        sel = [i for i in items if lo <= i["p"] < hi]
        if sel:
            buckets.append({"label": label, "n": len(sel), "avg_p": sum(i["p"] for i in sel) / len(sel),
                            "hit": sum(1 for i in sel if i["ok"]) / len(sel)})
    out["calibration"] = buckets

    # Altri mercati, solo per i pronostici che li avevano salvati
    ou = [(p["o25"] >= 0.5) == (m["hg"] + m["ag"] >= 3) for _, p, m in rows if p.get("o25") is not None]
    gg = [(p["gg"] >= 0.5) == (m["hg"] > 0 and m["ag"] > 0) for _, p, m in rows if p.get("gg") is not None]
    # Claude aiuta? Stessa partita, stesse metriche: probabilità finali contro sola statistica
    both = [(p, _outcome(m)) for _, p, m in rows if p.get("ai") and p.get("base")]
    if both:
        def br(q, a):
            return sum((q[k] - (1.0 if k == a else 0.0)) ** 2 for k in ("p1", "px", "p2"))
        def top(q):
            return max((("1", q["p1"]), ("X", q["px"]), ("2", q["p2"])), key=lambda x: x[1])[0]
        out["claude"] = {"n": len(both),
                         "brier_final": sum(br(p, a) for p, a in both) / len(both),
                         "brier_stat": sum(br(p["base"], a) for p, a in both) / len(both),
                         "hit_final": sum(1 for p, a in both if top(p) == a),
                         "hit_stat": sum(1 for p, a in both if top(p["base"]) == a)}
    # Modello nuovo (sola statistica) contro il vecchio, stesse partite
    cmp = [(p, _outcome(m)) for _, p, m in rows if p.get("old") and p.get("base")]
    if cmp:
        def br2(q, a):
            return sum((q[k] - (1.0 if k == a else 0.0)) ** 2 for k in ("p1", "px", "p2"))
        out["versions"] = {"n": len(cmp),
                           "brier_new": sum(br2(p["base"], a) for p, a in cmp) / len(cmp),
                           "brier_old": sum(br2(p["old"], a) for p, a in cmp) / len(cmp)}
    out["markets"] = {"ou": {"n": len(ou), "hit": sum(ou)}, "gg": {"n": len(gg), "hit": sum(gg)}}
    return out
