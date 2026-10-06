# Prima del Fischio

App che stima come potrebbe andare ogni partita di Serie A. Soluzione ibrida in tre livelli:

| Livello | Cosa fa | File |
|---|---|---|
| Dati | Risultati e calendario da football-data.org | `app/data.py` |
| Modello | Poisson con correzione sui punteggi bassi, forma recente, quote eque (1 / probabilità) | `app/model.py` |
| Claude | Cerca sul web infortuni e notizie, propone una correzione limitata (0,85-1,15) sui gol attesi e scrive la spiegazione con le fonti | `app/analyst.py` |

I numeri restano al modello, quindi sono stabili e verificabili. Claude non inventa probabilità né quote.
Le quote eque non sono quote di bookmaker: quelle vere richiedono un'API dedicata.

Ogni pronostico viene salvato in `data/predictions.db` prima della partita e mai riscritto
(`app/store.py`), poi confrontato con il risultato nella scheda Storico.

## Avvio

```bash
pip install -r requirements.txt
cp .env.example .env        # facoltativo: senza chiavi parte in modalità demo
uvicorn app.main:app --reload
```

Apri http://localhost:8000.

- **Senza chiavi**: dati inventati e analisi a regole (etichetta "Dati di esempio").
- **Con `FOOTBALL_DATA_KEY`**: dati reali del campionato (piano gratuito, Serie A inclusa).
- **Con anche `ANTHROPIC_API_KEY`**: Claude analizza ogni partita con ricerca web. I risultati
  sono in cache per 6 ore per contenere i costi.

## Limiti da conoscere

- A inizio stagione il modello ha pochi dati: le stime sono spostate verso la media del campionato.
- football-data.org non fornisce infortuni: li porta Claude dalla ricerca web, con le fonti mostrate.
- Le multiple mostrano la probabilità composta assumendo partite indipendenti.
