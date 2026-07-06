# LeakLane Desktop UI

Nuova interfaccia SvelteKit pensata per diventare la UI desktop della console
Gitleaks locale di LeakLane.

## Stato

- SvelteKit + TypeScript + Vite.
- Routing a pagine.
- Dashboard collegata a `/api/dashboard`.
- Ricerca repository e pitlane persistente nella pagina `Repository`.
- Setup Gitleaks/LM Studio e lancio job nella pagina `Scansione`.
- Report dettagliati, finding espandibili e Markdown AI nella pagina `Report`.
- Confronti collegati a `/api/diffs`.
- Archivio report collegato a `/api/jobs`.
- Settings collegata a `/api/prerequisites` per verificare backend, Git,
  Gitleaks, GitHub CLI e LM Studio.
- Configurazione Tauri v2 presente in `src-tauri/`, con avvio automatico del
  backend Python locale quando la porta `8787` non risponde.

Il backend Python esistente resta il punto di integrazione per Gitleaks,
GitHub CLI, LM Studio e persistenza report.

## Sviluppo web

Avvia prima il backend Python dalla root del progetto:

```bash
python3 web_app.py 8787
```

Poi avvia la nuova UI:

```bash
cd desktop-ui
npm run dev -- --port 5174
```

Apri:

```txt
http://127.0.0.1:5174/
```

## Build frontend

```bash
npm run check
npm run build
```

## Desktop con Tauri

Tauri richiede Rust/Cargo. Su questa macchina Rust e Cargo sono installati
tramite Homebrew e `npm run tauri:dev` e' stato validato.

Il launcher Tauri:

- usa `http://127.0.0.1:8787` come backend API in modalita' desktop;
- avvia `web_app.py` automaticamente se il backend non e' gia' attivo;
- salva i report nella cartella dati dell'app in produzione;
- include `web_app.py`, `scan_public_repos.py` e `web/` come risorse bundle.

```bash
cd desktop-ui
npm run tauri:dev
```

Per il primo packaging:

```bash
npm run tauri:build
```

## Prossime migrazioni

1. Verificare il packaging macOS con `npm run tauri:build`.
2. Rendere persistenti le preferenze utente della pagina Settings.
3. Aggiungere log visibili del backend desktop in caso di errore avvio.
4. Valutare una distribuzione con installer e notarizzazione macOS.
5. Preparare release notes e screenshot pubblici per il repository GitHub.
