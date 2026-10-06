"""Modello statistico: Poisson con correzione sui punteggi bassi.

Parte dai gol segnati/subiti in casa e fuori (con "shrinkage" verso la media del
campionato, perché a inizio stagione i campioni sono piccoli), applica la forma
recente e restituisce probabilità, risultati probabili e quote eque.
"""
import math
from collections import defaultdict

MAX_GOALS = 9
SHRINK_K = 4  # partite "virtuali" alla media del campionato


def pois(lam: float, k: int) -> float:
    p = math.exp(-lam)
    for i in range(1, k + 1):
        p *= lam / i
    return p


def form_points(form: str) -> int:
    return sum(3 if c == "V" else 1 if c == "N" else 0 for c in form)


def form_factor(form: str) -> float:
    if not form:
        return 1.0
    return 0.94 + 0.12 * form_points(form) / (3 * len(form))


def build_teams(finished: list[dict]) -> tuple[dict, float, float]:
    """finished: [{date, home, away, hg, ag}] -> (teams, avg_h, avg_a)."""
    avg_h = sum(m["hg"] for m in finished) / len(finished)
    avg_a = sum(m["ag"] for m in finished) / len(finished)
    acc = defaultdict(lambda: {"hn": 0, "hgf": 0, "hga": 0, "an": 0, "agf": 0, "aga": 0, "res": []})

    def res(gf, ga):
        return "V" if gf > ga else "N" if gf == ga else "P"

    for m in sorted(finished, key=lambda x: x["date"]):
        h, a = acc[m["home"]], acc[m["away"]]
        h["hn"] += 1; h["hgf"] += m["hg"]; h["hga"] += m["ag"]; h["res"].append(res(m["hg"], m["ag"]))
        a["an"] += 1; a["agf"] += m["ag"]; a["aga"] += m["hg"]; a["res"].append(res(m["ag"], m["hg"]))

    k = SHRINK_K
    teams = {}
    for name, s in acc.items():
        teams[name] = {
            "hgf": (s["hgf"] + k * avg_h) / (s["hn"] + k),
            "hga": (s["hga"] + k * avg_a) / (s["hn"] + k),
            "agf": (s["agf"] + k * avg_a) / (s["an"] + k),
            "aga": (s["aga"] + k * avg_h) / (s["an"] + k),
            "form": "".join(s["res"][-5:]),
        }
    return teams, avg_h, avg_a


def _team(teams: dict, name: str, avg_h: float, avg_a: float) -> dict:
    # Squadra senza partite (es. neopromossa a inizio stagione): media del campionato
    return teams.get(name) or {"hgf": avg_h, "hga": avg_a, "agf": avg_a, "aga": avg_h, "form": ""}


def expected_goals(teams: dict, avg_h: float, avg_a: float, home: str, away: str) -> tuple[float, float]:
    H, A = _team(teams, home, avg_h, avg_a), _team(teams, away, avg_h, avg_a)
    lh = H["hgf"] * A["aga"] / avg_h * form_factor(H["form"])
    la = A["agf"] * H["hga"] / avg_a * form_factor(A["form"])
    return lh, la


def summarize(lh: float, la: float) -> dict:
    cells, total = [], 0.0
    for i in range(MAX_GOALS):
        for j in range(MAX_GOALS):
            p = pois(lh, i) * pois(la, j)
            if i == j and i <= 1:
                p *= 1.08
            elif i + j == 1:
                p *= 0.94
            cells.append((i, j, p))
            total += p
    r = dict(p1=0.0, px=0.0, p2=0.0, o15=0.0, o25=0.0, u35=0.0, gg=0.0)
    scores = []
    for i, j, p in cells:
        q = p / total
        if i > j: r["p1"] += q
        elif i == j: r["px"] += q
        else: r["p2"] += q
        if i + j >= 2: r["o15"] += q
        if i + j >= 3: r["o25"] += q
        if i + j <= 3: r["u35"] += q
        if i > 0 and j > 0: r["gg"] += q
        scores.append((i, j, q))
    scores.sort(key=lambda s: -s[2])
    r["u25"] = 1 - r["o25"]
    r["ng"] = 1 - r["gg"]
    top = max(r["p1"], r["px"], r["p2"])
    r["conf"] = "alta" if top >= 0.55 else "media" if top >= 0.45 else "bassa"
    r["top_scores"] = [[i, j, round(q, 4)] for i, j, q in scores[:3]]
    return r


def fair_odds(p: float) -> float | None:
    """Quota equa = 1 / probabilità. Non è una quota di bookmaker."""
    return round(1 / p, 2) if p > 0.001 else None
