# Gator Quant Hacks 2026 · Trade the 8-K

Starter notebook for the Massive challenge. You need **Python 3.10+** ([python.org](https://www.python.org/downloads/))
and a **Massive API key** (from the Discord channel).

## Layout (inside this repo)

```
massive/gqh-massive-8k-starter/
├── gator-quant-hacks-8k-options-challenge.ipynb
├── requirements.txt
├── setup.ps1 / setup.sh
├── .env.example
├── .env                 ← local only (gitignored); optional if infra key exists
├── .venv/               ← created by setup (gitignored)
└── .massive_cache/      ← created on first run (gitignored)
```

In **GQHacks**, the notebook also reads `MASSIVE_API_KEY` / `MASSIVE_APP_KEY` from
`infrastructure/backtest/.env` (and a few track `.env` files) if the starter `.env`
is missing or still has the placeholder. Cache files land under this folder even when
you open the notebook from the repo root in Cursor/VS Code.

## Setup (about 2 minutes)

**macOS / Linux** — in a terminal, from this folder:

```bash
./setup.sh
```

**Windows** — in PowerShell, from this folder:

```powershell
powershell -ExecutionPolicy Bypass -File setup.ps1
```

The script creates a `.venv`, installs `requirements.txt`, registers the Jupyter kernel
**Python (Gator Quant Hacks .venv)**, and creates `.env` from `.env.example`. It is safe to re-run.

Then:

1. Open `.env` and replace `your-key-here` with your key (no spaces or quotes),
   **or** rely on `infrastructure/backtest/.env` already used by the tracks.
2. In Cursor/VS Code: open the `.ipynb`, pick kernel **Python (Gator Quant Hacks .venv)**,
   Run All. Or: `.venv\Scripts\activate; jupyter lab`
3. Section 1 should print `API key loaded (ends xxxx)`. First full run ~10 minutes;
   later runs use `.massive_cache/`.

## Manual setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python -m pip install -r requirements.txt
python -m ipykernel install --user --name gator-quant-hacks --display-name "Python (Gator Quant Hacks .venv)"
cp .env.example .env               # then add your key
```

Already have a Jupyter environment (Colab, an existing kernel)? Skip all of this and run the
optional `%pip install -r requirements.txt` cell at the top of the notebook, then restart the kernel.

## Troubleshooting

- **"Kernel not found" when opening the notebook** — run the setup script, or just pick any Python 3.10+ kernel.
- **`ModuleNotFoundError`** — the notebook is on a different kernel than the one you installed into.
  Run `import sys; print(sys.executable)` in a cell; it should end in `.venv\Scripts\python.exe` (Windows)
  or `.venv/bin/python`.
- **Prompted for an API key** — no usable key in env / starter `.env` / `infrastructure/backtest/.env`.
- **Slow iteration** — set `RUN_PLACEBO = False` in section 2 while exploring (saves ~8 minutes per
  run); turn it back on before you submit.
- **Stale recent data** — the cache never expires. Delete `.massive_cache/` to refetch.

Keep `.env` out of anything you share or submit; `.gitignore` already excludes it.
