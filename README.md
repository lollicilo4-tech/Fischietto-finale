# Fischietto finale

App che stima come potrebbe andare ogni partita di Serie A. Soluzione ibrida in tre livelli:

| Livello | Cosa fa | File |
|---|---|---|
| Dati | Risultati e calendario da football-data.org | `app/data.py` |
| Modello | Poisson con correzione sui punteggi bassi, forma recente, quote eque (1 / probabilità) | `app/model.py` |
| Claude | Cerca sul web infortuni e notizie, propone una correzione limitata (0,85-1,15) sui gol attesi e scrive la spiegazione con le fonti | `app/analyst.py` |

I numeri restano al modello, quindi sono stabili e verificabili. Claude non inventa probabilità né quote.
Le quote eque non sono quote di bookmaker: quelle vere richiedono un'API dedicata.

Ogni pronostico viene salvato in `data/predictions.json` prima della partita e mai riscritto
(`app/store.py`), poi confrontato con il risultato nella scheda Storico.

## Prova in locale

```bash
py -m pip install -r requirements.txt
copy .env.example .env      # poi inserisci le chiavi in .env; senza chiavi parte in demo
py -m uvicorn app.main:app --reload
```

Apri http://localhost:8000.

- **Senza chiavi**: dati inventati e analisi a regole (etichetta "Dati di esempio").
- **Con `FOOTBALL_DATA_KEY`**: dati reali del campionato (piano gratuito, Serie A inclusa).
- **Con anche `ANTHROPIC_API_KEY`** (inizia con `sk-ant-`): Claude analizza ogni partita con ricerca web.

## Pubblicazione gratuita

Il sito online è statico: un'automazione di GitHub (`.github/workflows/update.yml`) esegue `generate.py`
due volte al giorno, scrive i dati nella cartella `docs/` e la pubblica. I visitatori non fanno mai
partire chiamate a football-data.org o a Claude, quindi il costo di Claude è fisso (circa 20 analisi al giorno)
e non dipende dal traffico. Il server può restare spento, il sito è sempre acceso e lo Storico non si perde.

1. **GitHub**: crea un account su github.com e un repository nuovo (anche privato).
2. **Carica il progetto con GitHub Desktop**, non trascinando i file nel browser: GitHub Desktop rispetta
   `.gitignore` e non carica il file `.env` con le chiavi. Verifica comunque che `.env.example` abbia le righe
   delle chiavi vuote.
3. **Secrets**: nel repository apri Settings, Secrets and variables, Actions, e crea `FOOTBALL_DATA_KEY` e
   `ANTHROPIC_API_KEY` con le tue chiavi.
4. **Prima generazione**: scheda Actions, "Aggiorna pronostici", Run workflow. In un paio di minuti compare
   la cartella `docs/` con il sito.
5. **Pubblica `docs/`** con uno di questi:
   - GitHub Pages: Settings, Pages, Source "Deploy from a branch", branch `main`, cartella `/docs`.
   - Cloudflare Pages: collega il repository, build command vuoto, output directory `docs`.
6. Nella console Anthropic imposta un **limite di spesa mensile**, come rete di sicurezza.

## Pubblicità

Parti senza. Google AdSense richiede approvazione, un'informativa privacy e, in Europa, il consenso ai cookie
tramite un sistema certificato; di solito conviene un dominio tuo. Prima di attivarla controlla i termini del
servizio che ospita il sito e le regole italiane sulla comunicazione legata al gioco. La licenza gratuita di
football-data.org richiede l'attribuzione, già presente nel piè di pagina.

## Limiti da conoscere

- A inizio stagione il modello ha pochi dati: le stime sono spostate verso la media del campionato.
- football-data.org non fornisce infortuni: li porta Claude dalla ricerca web, con le fonti mostrate.
- Le multiple mostrano la probabilità composta assumendo partite indipendenti.
- Durante le pause per le nazionali non ci sono partite in programma e il sito resta fermo all'ultimo turno.
