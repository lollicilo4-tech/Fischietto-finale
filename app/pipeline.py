"""Costruisce i dati del turno e dello storico.

Usato sia dal server locale (app/main.py) sia dal generatore del sito statico (generate.py).
"""
from datetime import datetime, timezone

from . import analyst, data, model, store

KEYS = ["p1", "px", "p2", "o15", "o25", "u25", "u35", "gg", "ng"]

DEMO_HISTORY = {
    "demo": True, "n": 8, "hit": 6, "avg_p": 0.7075,
    "items": [
        {"match": m, "pick": k, "p": p, "score": s, "ok": ok} for m, k, p, s, ok in [
            ("Inter – Genoa", "1", 0.91, "3-0", True), ("Milan – Lazio", "1", 0.57, "1-1", False),
            ("Juventus – Como", "1", 0.62, "2-0", True), ("Atalanta – Roma", "1", 0.81, "2-1", True),
            ("Bologna – Udinese", "1", 0.78, "1-0", True), ("Fiorentina – Genoa", "1", 0.79, "2-0", True),
            ("Lecce – Cagliari", "2", 0.60, "1-1", False), ("Napoli – Torino", "1", 0.66, "2-0", True),
        ]
    ],
}


async def build_turno() -> dict:
    ctx = await data.get_context()
    teams, avg_h, avg_a = ctx["teams"], ctx["avg_h"], ctx["avg_a"]

    bases = []
    for fx in ctx["fixtures"]:
        lh, la = model.expected_goals(teams, avg_h, avg_a, fx["home"], fx["away"])
        base = model.summarize(lh, la)
        base.update(lh=lh, la=la)
        bases.append({"fx": fx, "base": base})

    analyses = await analyst.analyze_all(bases, teams, use_ai=not ctx["demo"])

    out = []
    for item, an in zip(bases, analyses):
        fx = item["fx"]
        # Il modello ricalcola le probabilità con i fattori proposti da Claude (limitati a 0,85-1,15)
        lh, la = item["base"]["lh"] * an["factor_home"], item["base"]["la"] * an["factor_away"]
        s = model.summarize(lh, la)
        if not an["ai"]:  # il testo a regole deve citare le stesse cifre mostrate nella scheda
            an["text"] = analyst.fallback_analysis(fx, {**s, "lh": lh, "la": la}, teams)["text"]
        prob = {k: round(s[k], 4) for k in KEYS}
        out.append({
            "id": fx["id"], "home": fx["home"], "away": fx["away"], "kickoff": fx["kickoff"], "label": fx["label"],
            "prob": prob, "fair_odds": {k: model.fair_odds(prob[k]) for k in KEYS},
            "xg": [round(lh, 2), round(la, 2)], "xg_base": [round(item["base"]["lh"], 2), round(item["base"]["la"], 2)],
            "top_scores": s["top_scores"], "conf": s["conf"],
            "form": {"home": teams.get(fx["home"], {}).get("form", ""), "away": teams.get(fx["away"], {}).get("form", "")},
            "analysis": {k: an[k] for k in ("ai", "text", "factor_home", "factor_away",
                                            "absences_home", "absences_away", "sources")},
        })
        if not ctx["demo"]:
            store.save(fx["id"], fx["home"], fx["away"], fx["kickoff"], prob["p1"], prob["px"], prob["p2"])

    return {"demo": ctx["demo"], "ai": any(a["ai"] for a in analyses),
            "ai_error": next((a.get("reason") for a in analyses if a.get("reason")), None),
            "matchday": ctx.get("matchday"),
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="minutes"),
            "matches": out}


async def build_storico() -> dict:
    if not data.has_key():
        return DEMO_HISTORY
    ctx = await data.get_context()
    return {"demo": False, **store.history(ctx["finished"])}
