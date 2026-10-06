"""Livello AI: Claude con ricerca web legge le notizie (infortuni, squalifiche,
probabili formazioni) e propone due cose, entrambe tracciate nella risposta:

- un fattore di correzione sui gol attesi di ciascuna squadra, limitato a 0,85-1,15
- una spiegazione in italiano basata solo su ciò che ha trovato

I numeri restano al modello statistico: Claude non inventa probabilità né quote.
"""
import asyncio
import json
import os
import time

FACTOR_MIN, FACTOR_MAX = 0.85, 1.15
CACHE_SECONDS = 6 * 3600
_cache: dict = {}
ROLE = {"att": "attaccante titolare", "def": "difensore titolare"}

SYSTEM = """Sei l'analista di un'app che spiega come potrebbe andare una partita di calcio.
Cerca sul web notizie recenti (ultime 72 ore) su queste due squadre: infortuni, squalifiche,
probabili formazioni, turnover, cambi di allenatore, impegni ravvicinati.
Usa solo ciò che trovi in fonti affidabili. Se non trovi nulla di rilevante, dillo e usa fattore 1.0.
Non citare quote dei bookmaker e non incoraggiare a scommettere.
Rispondi SOLO con un oggetto JSON, senza altro testo, con questi campi:
{"assenze_casa": [str], "assenze_trasferta": [str],
 "fattore_gol_casa": numero tra 0.85 e 1.15, "fattore_gol_trasferta": numero tra 0.85 e 1.15,
 "spiegazione": "3-4 frasi in italiano, chiare, coerenti con i numeri del modello"}
Il fattore moltiplica i gol attesi della squadra: sotto 1 se le assenze ne riducono l'attacco
(o se l'avversario perde un difensore importante, alza invece l'altra squadra)."""


def _clip(x, default=1.0) -> float:
    try:
        return max(FACTOR_MIN, min(FACTOR_MAX, float(x)))
    except (TypeError, ValueError):
        return default


def pc(p: float) -> str:
    return f"{round(p * 100)}%"


def d1(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def fallback_analysis(fx: dict, base: dict, teams: dict) -> dict:
    """Senza AI: assenze dai dati (solo demo) e testo a regole."""
    H, A = teams.get(fx["home"], {}), teams.get(fx["away"], {})
    fh = fa = 1.0
    for x in H.get("abs", []):
        fh *= 0.93 if x == "att" else 1.0
        fa *= 1.06 if x == "def" else 1.0
    for x in A.get("abs", []):
        fa *= 0.93 if x == "att" else 1.0
        fh *= 1.06 if x == "def" else 1.0
    parts = [f"Il modello stima {d1(base['lh'])} gol per {fx['home']} e {d1(base['la'])} per {fx['away']}."]
    if base["p1"] >= 0.5:
        parts.append(f"{fx['home']} parte favorita ({pc(base['p1'])}), anche grazie al fattore campo.")
    elif base["p2"] >= 0.5:
        parts.append(f"{fx['away']} è favorita anche in trasferta ({pc(base['p2'])}).")
    else:
        parts.append("Partita aperta: nessun esito supera il 50%.")
    if base["px"] >= 0.28:
        parts.append(f"Il pareggio resta credibile ({pc(base['px'])}).")
    return {
        "ai": False, "text": " ".join(parts), "factor_home": fh, "factor_away": fa,
        "absences_home": [ROLE[x] for x in H.get("abs", [])],
        "absences_away": [ROLE[x] for x in A.get("abs", [])], "sources": [],
    }


def _parse_json(text: str) -> dict:
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        raise ValueError("risposta senza JSON")
    return json.loads(text[a:b + 1])


async def _ask_claude(client, fx: dict, base: dict) -> dict:
    kickoff = fx.get("kickoff") or "prossimo turno"
    user = (
        f"Partita: {fx['home']} (casa) contro {fx['away']} (trasferta), {kickoff}.\n"
        f"Numeri del modello statistico: gol attesi {d1(base['lh'])} - {d1(base['la'])}; "
        f"1 {pc(base['p1'])}, X {pc(base['px'])}, 2 {pc(base['p2'])}."
    )
    messages = [{"role": "user", "content": user}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": 4}]
    resp = None
    for _ in range(3):  # gestisce l'eventuale pausa del turno di ricerca
        resp = await client.messages.create(
            model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"), max_tokens=1500,
            system=SYSTEM, tools=tools, messages=messages,
        )
        if resp.stop_reason != "pause_turn":
            break
        messages.append({"role": "assistant", "content": resp.content})

    text, sources, seen = "", [], set()
    for block in resp.content:
        if block.type == "text":
            text += block.text
            for c in getattr(block, "citations", None) or []:
                url = getattr(c, "url", None)
                if url and url not in seen:
                    seen.add(url)
                    sources.append({"title": getattr(c, "title", url), "url": url})
    data = _parse_json(text)
    return {
        "ai": True, "text": str(data.get("spiegazione", "")).strip(),
        "factor_home": _clip(data.get("fattore_gol_casa")), "factor_away": _clip(data.get("fattore_gol_trasferta")),
        "absences_home": [str(x) for x in data.get("assenze_casa", [])][:5],
        "absences_away": [str(x) for x in data.get("assenze_trasferta", [])][:5],
        "sources": sources[:5],
    }


async def analyze_all(items: list[dict], teams: dict, use_ai: bool) -> list[dict]:
    """items: [{"fx": fixture, "base": {lh, la, p1, px, p2, ...}}]"""
    if not (use_ai and os.getenv("ANTHROPIC_API_KEY")):
        return [fallback_analysis(i["fx"], i["base"], teams) for i in items]

    from anthropic import AsyncAnthropic
    client = AsyncAnthropic()
    sem = asyncio.Semaphore(3)

    async def one(item):
        fx = item["fx"]
        hit = _cache.get(fx["id"])
        if hit and time.time() - hit[0] < CACHE_SECONDS:
            return hit[1]
        async with sem:
            try:
                out = await _ask_claude(client, fx, item["base"])
            except Exception as exc:  # rete, JSON non valido, limiti: si ripiega sulle regole
                print(f"[analyst] {fx['home']}-{fx['away']}: {exc!r}")
                return fallback_analysis(fx, item["base"], teams)
        _cache[fx["id"]] = (time.time(), out)
        return out

    return await asyncio.gather(*(one(i) for i in items))
