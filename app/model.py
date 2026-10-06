"""Modello statistico: Poisson con correzione sui punteggi bassi.

Ogni squadra ha una forza in attacco e una in difesa, stimate tenendo conto di chi ha affrontato
(segnare alla più forte vale di più) e dando più peso alle partite recenti. Come punto di partenza
si usa anche la stagione scorsa. Restituisce probabilità, risultati probabili e quote eque.
"""
import math

MAX_GOALS = 9


def pois(lam: float, k: int) -> float:
    p = math.exp(-lam)
    for i in range(1, k + 1):
        p *= lam / i
    return p


def form_points(form: str) -> int:
    return sum(3 if c == "V" else 1 if c == "N" else 0 for c in form)


def form_factor(form: str) -> float:
    """Piccolo ritocco per la forma: con il peso dato alle partite recenti il grosso è già nel modello."""
    if not form:
        return 1.0
    return 0.97 + 0.06 * form_points(form) / (3 * len(form))


HALF_LIFE = 120  # giorni: una partita di quattro mesi fa pesa la metà di una di oggi
PRIOR_K = 8.0    # peso virtuale della media del campionato (evita stime estreme con pochi dati)
UNKNOWN = {"att": 0.92, "def": 1.08, "form": ""}  # squadra senza storico (neopromossa): un filo sotto la media


def _days(date: str, now) -> float:
    from datetime import datetime, timezone
    d = datetime.fromisoformat(date.replace("Z", "+00:00"))
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return max((now - d).total_seconds() / 86400, 0.0)


def build_teams(finished: list[dict], previous: list[dict] | None = None, now=None) -> tuple[dict, float, float]:
    """Forza di attacco e difesa di ogni squadra, corretta per il livello degli avversari.

    - finished: partite della stagione in corso [{date, home, away, hg, ag}]
    - previous: partite della stagione scorsa, usate come punto di partenza (pesano meno col passare dei giorni)
    Ritorna (teams, media gol in casa, media gol fuori).
    """
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    games = [(m, _days(m["date"], now)) for m in (previous or []) + finished]
    games = [(m, 0.5 ** (d / HALF_LIFE)) for m, d in games]

    wsum = sum(w for _, w in games)
    mu_h = sum(w * m["hg"] for m, w in games) / wsum
    mu_a = sum(w * m["ag"] for m, w in games) / wsum

    names = {m["home"] for m, _ in games} | {m["away"] for m, _ in games}
    att = {t: 1.0 for t in names}
    dff = {t: 1.0 for t in names}
    for _ in range(80):
        an, ad, dn, dd = ({t: 0.0 for t in names} for _ in range(4))
        for m, w in games:
            h, a = m["home"], m["away"]
            an[h] += w * m["hg"]; ad[h] += w * mu_h * dff[a]
            an[a] += w * m["ag"]; ad[a] += w * mu_a * dff[h]
            dn[h] += w * m["ag"]; dd[h] += w * mu_a * att[a]
            dn[a] += w * m["hg"]; dd[a] += w * mu_h * att[h]
        na = {t: (an[t] + PRIOR_K) / (ad[t] + PRIOR_K) for t in names}
        nd = {t: (dn[t] + PRIOR_K) / (dd[t] + PRIOR_K) for t in names}
        ma, md = sum(na.values()) / len(na), sum(nd.values()) / len(nd)
        # media tra vecchio e nuovo valore (damping): evita oscillazioni e converge sempre
        att = {t: math.sqrt(att[t] * na[t] / ma) for t in names}
        dff = {t: math.sqrt(dff[t] * nd[t] / md) for t in names}

    def res(gf, ga):
        return "V" if gf > ga else "N" if gf == ga else "P"

    forms: dict[str, list] = {}
    for m in sorted(finished, key=lambda x: x["date"]):
        forms.setdefault(m["home"], []).append(res(m["hg"], m["ag"]))
        forms.setdefault(m["away"], []).append(res(m["ag"], m["hg"]))
    teams = {t: {"att": att[t], "def": dff[t], "form": "".join(forms.get(t, [])[-5:])} for t in names}
    return teams, mu_h, mu_a


def build_teams_simple(finished: list[dict], k: int = 4) -> tuple[dict, float, float]:
    """Il modello della prima versione (gol fatti/subiti in casa e fuori, tutti con lo stesso peso).
    Resta attivo "in ombra": il suo pronostico viene salvato accanto al nuovo, per confrontarli sui risultati veri."""
    from collections import defaultdict
    avg_h = sum(m["hg"] for m in finished) / len(finished)
    avg_a = sum(m["ag"] for m in finished) / len(finished)
    acc = defaultdict(lambda: {"hn": 0, "hgf": 0, "hga": 0, "an": 0, "agf": 0, "aga": 0, "res": []})
    for m in sorted(finished, key=lambda x: x["date"]):
        h, a = acc[m["home"]], acc[m["away"]]
        h["hn"] += 1; h["hgf"] += m["hg"]; h["hga"] += m["ag"]; h["res"].append("V" if m["hg"] > m["ag"] else "N" if m["hg"] == m["ag"] else "P")
        a["an"] += 1; a["agf"] += m["ag"]; a["aga"] += m["hg"]; a["res"].append("V" if m["ag"] > m["hg"] else "N" if m["hg"] == m["ag"] else "P")
    teams = {n: {"hgf": (s["hgf"] + k * avg_h) / (s["hn"] + k), "hga": (s["hga"] + k * avg_a) / (s["hn"] + k),
                 "agf": (s["agf"] + k * avg_a) / (s["an"] + k), "aga": (s["aga"] + k * avg_h) / (s["an"] + k),
                 "form": "".join(s["res"][-5:])} for n, s in acc.items()}
    return teams, avg_h, avg_a


def expected_goals_simple(teams: dict, avg_h: float, avg_a: float, home: str, away: str) -> tuple[float, float]:
    dflt = {"hgf": avg_h, "hga": avg_a, "agf": avg_a, "aga": avg_h, "form": ""}
    H, A = teams.get(home) or dflt, teams.get(away) or dflt
    ff = lambda f: 0.94 + 0.12 * form_points(f) / (3 * len(f)) if f else 1.0
    return H["hgf"] * A["aga"] / avg_h * ff(H["form"]), A["agf"] * H["hga"] / avg_a * ff(A["form"])


def expected_goals(teams: dict, avg_h: float, avg_a: float, home: str, away: str) -> tuple[float, float]:
    H, A = teams.get(home), teams.get(away)
    if (H and "att" not in H) or (A and "att" not in A):  # dati di esempio, vecchio formato
        return _expected_goals_demo(teams, avg_h, avg_a, home, away)
    H, A = H or UNKNOWN, A or UNKNOWN
    lh = avg_h * H["att"] * A["def"] * form_factor(H["form"])
    la = avg_a * A["att"] * H["def"] * form_factor(A["form"])
    return lh, la


def _expected_goals_demo(teams: dict, avg_h: float, avg_a: float, home: str, away: str) -> tuple[float, float]:
    H, A = teams[home], teams[away]
    return (H["hgf"] * A["aga"] / avg_h * form_factor(H["form"]),
            A["agf"] * H["hga"] / avg_a * form_factor(A["form"]))


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
