"""Fonte dati: football-data.org (piano gratuito, Serie A = "SA").

Senza chiave FOOTBALL_DATA_KEY parte la modalità demo con dati inventati.
"""
import os
import time

import httpx

BASE = "https://api.football-data.org/v4"
COMPETITION = os.getenv("COMPETITION", "SA")
_cache: dict = {"t": 0.0, "v": None}
CACHE_SECONDS = 30 * 60  # il piano gratuito ha 10 richieste al minuto

# --- Demo ------------------------------------------------------------------
DEMO_TEAMS = {
    "Inter": dict(hgf=2.3, hga=0.7, agf=1.9, aga=0.9, form="VVVNV", abs=[]),
    "Napoli": dict(hgf=1.9, hga=0.8, agf=1.5, aga=1.0, form="VVNVV", abs=["def"]),
    "Milan": dict(hgf=1.7, hga=0.9, agf=1.4, aga=1.0, form="VNVVP", abs=[]),
    "Juventus": dict(hgf=1.6, hga=0.8, agf=1.3, aga=0.9, form="NVNVV", abs=["att"]),
    "Atalanta": dict(hgf=2.0, hga=1.0, agf=1.7, aga=1.2, form="VVPVN", abs=[]),
    "Roma": dict(hgf=1.5, hga=0.8, agf=1.2, aga=1.0, form="VNVPV", abs=[]),
    "Lazio": dict(hgf=1.5, hga=1.1, agf=1.2, aga=1.3, form="PVNVP", abs=[]),
    "Fiorentina": dict(hgf=1.4, hga=1.1, agf=1.1, aga=1.3, form="NPVNN", abs=[]),
    "Bologna": dict(hgf=1.4, hga=1.0, agf=1.1, aga=1.2, form="VPNVN", abs=["att"]),
    "Torino": dict(hgf=1.2, hga=1.1, agf=0.9, aga=1.4, form="NPNVP", abs=[]),
    "Genoa": dict(hgf=1.1, hga=1.2, agf=0.9, aga=1.5, form="PNPNV", abs=[]),
    "Udinese": dict(hgf=1.2, hga=1.3, agf=0.8, aga=1.5, form="PPNVP", abs=[]),
    "Como": dict(hgf=1.5, hga=1.2, agf=1.2, aga=1.4, form="VNPVN", abs=[]),
    "Cagliari": dict(hgf=1.1, hga=1.3, agf=0.8, aga=1.6, form="PPNPV", abs=[]),
    "Parma": dict(hgf=1.2, hga=1.3, agf=0.9, aga=1.6, form="NPPVN", abs=[]),
    "Lecce": dict(hgf=1.0, hga=1.2, agf=0.7, aga=1.5, form="NPNPP", abs=["att"]),
    "Verona": dict(hgf=1.1, hga=1.5, agf=0.8, aga=1.8, form="PPPNP", abs=[]),
    "Sassuolo": dict(hgf=1.4, hga=1.6, agf=1.1, aga=1.7, form="VPPVN", abs=[]),
    "Pisa": dict(hgf=1.0, hga=1.4, agf=0.7, aga=1.7, form="PNPPN", abs=[]),
    "Cremonese": dict(hgf=1.0, hga=1.3, agf=0.8, aga=1.6, form="NPPNP", abs=["def"]),
}
DEMO_FIXTURES = [
    ("Inter", "Genoa", "Sab 15:00"), ("Napoli", "Torino", "Sab 18:00"), ("Milan", "Udinese", "Sab 20:45"),
    ("Juventus", "Fiorentina", "Dom 12:30"), ("Atalanta", "Cagliari", "Dom 15:00"), ("Roma", "Bologna", "Dom 18:00"),
    ("Lazio", "Como", "Dom 20:45"), ("Parma", "Lecce", "Dom 15:00"), ("Verona", "Sassuolo", "Dom 15:00"),
    ("Pisa", "Cremonese", "Dom 15:00"),
]


def demo_context() -> dict:
    n = len(DEMO_TEAMS)
    return {
        "demo": True,
        "teams": DEMO_TEAMS,
        "avg_h": sum(t["hgf"] for t in DEMO_TEAMS.values()) / n,
        "avg_a": sum(t["agf"] for t in DEMO_TEAMS.values()) / n,
        "fixtures": [
            {"id": f"demo-{i}", "home": h, "away": a, "kickoff": None, "label": w}
            for i, (h, a, w) in enumerate(DEMO_FIXTURES)
        ],
        "finished": [],
    }


# --- Dati reali ------------------------------------------------------------
def has_key() -> bool:
    return bool(os.getenv("FOOTBALL_DATA_KEY"))


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict:
    r = await client.get(f"{BASE}{path}", params=params,
                         headers={"X-Auth-Token": os.environ["FOOTBALL_DATA_KEY"]}, timeout=20)
    r.raise_for_status()
    return r.json()


def _name(t: dict) -> str:
    return t.get("shortName") or t["name"]


def _standings(st: dict) -> list[dict]:
    tables = [t for t in st.get("standings", []) if t.get("type") == "TOTAL"] or st.get("standings", [])
    if not tables:
        return []
    return [{"pos": r["position"], "team": _name(r["team"]), "pg": r["playedGames"], "w": r["won"],
             "d": r["draw"], "l": r["lost"], "gf": r["goalsFor"], "ga": r["goalsAgainst"], "pts": r["points"]}
            for r in tables[0]["table"]]


async def real_context() -> dict:
    from . import model

    async with httpx.AsyncClient() as client:
        fin = await _get(client, f"/competitions/{COMPETITION}/matches", {"status": "FINISHED"})
        sch = await _get(client, f"/competitions/{COMPETITION}/matches", {"status": "SCHEDULED,TIMED"})
        previous = []
        try:  # stagione scorsa: serve a non partire da zero nelle prime giornate
            first = min(m["utcDate"] for m in sch["matches"]) if sch["matches"] else None
            if first:
                y = int(first[:4]) - (1 if int(first[5:7]) < 7 else 0)
                prev = await _get(client, f"/competitions/{COMPETITION}/matches", {"season": y - 1, "status": "FINISHED"})
                previous = [{"id": str(m["id"]), "date": m["utcDate"], "home": _name(m["homeTeam"]),
                             "away": _name(m["awayTeam"]), "hg": m["score"]["fullTime"]["home"],
                             "ag": m["score"]["fullTime"]["away"]}
                            for m in prev["matches"] if m["score"]["fullTime"]["home"] is not None]
        except (httpx.HTTPError, KeyError, ValueError):
            previous = []
        try:  # la classifica è un di più: se manca, il resto funziona lo stesso
            st = await _get(client, f"/competitions/{COMPETITION}/standings", {})
        except httpx.HTTPError:
            st = {}

    finished = [
        {"id": str(m["id"]), "date": m["utcDate"], "home": _name(m["homeTeam"]), "away": _name(m["awayTeam"]),
         "hg": m["score"]["fullTime"]["home"], "ag": m["score"]["fullTime"]["away"]}
        for m in fin["matches"] if m["score"]["fullTime"]["home"] is not None
    ]
    if not finished:
        raise RuntimeError("Nessuna partita giocata: il modello ha bisogno di almeno qualche giornata.")
    teams, avg_h, avg_a = model.build_teams(finished, previous)

    upcoming = sorted(sch["matches"], key=lambda m: m["utcDate"])
    if not upcoming:
        raise RuntimeError("Nessuna partita in programma.")
    matchday = min(m["matchday"] for m in upcoming)
    fixtures = [
        {"id": str(m["id"]), "home": _name(m["homeTeam"]), "away": _name(m["awayTeam"]),
         "kickoff": m["utcDate"], "label": None}
        for m in upcoming if m["matchday"] == matchday
    ]
    simple = model.build_teams_simple(finished)
    return {"demo": False, "teams_simple": simple, "teams": teams, "avg_h": avg_h, "avg_a": avg_a,
            "fixtures": fixtures, "finished": finished, "matchday": matchday,
            "previous": previous,
            "standings": _standings(st)}


async def get_context() -> dict:
    if not has_key():
        return demo_context()
    if _cache["v"] and time.time() - _cache["t"] < CACHE_SECONDS:
        return _cache["v"]
    ctx = await real_context()
    _cache.update(t=time.time(), v=ctx)
    return ctx
