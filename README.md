# Detective Conan Card Game — Collection Tracker

A full-stack personal collection tracker for the [Detective Conan Card Game](https://www.takaratomy.co.jp/products/conan-cardgame). Scrapes card data from the official Takara Tomy site, stores it in a normalized SQLite database, and serves it through a Flask web app with filtering, quantity tracking, a personal watchlist, and a natural language AI query interface.

---

## Features

- Scrapes all card data and images from the official card list
- Normalized SQLite database with packages, types, rarities, colors, and categories
- Preview scraped changes before committing to the database
- Field-level ignore rules to override known errors on the official site
- Flask web app with virtual-scrolling card grid
- Per-card quantity tracking and personal watchlist
- Thumbnail generation for fast page loads
- Agentic AI query interface — ask questions in plain English, the agent runs multiple queries as needed and returns a synthesized answer

---

## Experimental

An agentic AI query interface is in active development on the [`llm-sql-query`](https://github.com/kevin791129/ConanTCG/tree/llm-sql-query) branch. It allows querying the card collection in plain English using a multi-step Text-to-SQL pipeline with support for Anthropic and Google Gemini models.

---

## Project Structure

```
ConanTCG/
├── run.py                      # App entrypoint
├── .env                        # Local config (gitignored)
├── .env.example                # Config template
├── sync_cards.ignore.json      # Field-level overrides for known site errors
├── requirements.txt
│
├── app/
│   ├── __init__.py             # Flask app factory
│   ├── db.py                   # Request-scoped DB connection
│   ├── queries.py              # SQL queries
│   ├── routes/
│   │   ├── collection.py       # Collection and watchlist pages
│   │   ├── api.py              # JSON API endpoints
│   │   └── ai.py               # AI query page and endpoints
│   └── ai/
│       ├── prompt.py           # System prompt and schema description
│       ├── pipeline.py         # Agentic Text-to-SQL pipeline
│       └── providers/
│           ├── base.py         # Abstract provider interface
│           ├── anthropic.py    # Anthropic provider
│           └── gemini.py       # Google Gemini provider
│
├── scripts/
│   ├── create_database.py      # Initialize the SQLite database
│   ├── sync_cards.py           # Scraper and card importer
│   ├── set_sort_orders.py      # Set filter sort orders
│   └── create_ai_query_log.py  # Initialize the AI query log database
│
├── templates/
│   ├── base.html
│   ├── collection.html
│   ├── watchlist.html
│   └── ai.html                 # Natural language query page
│
└── static/
    ├── css/
    ├── images/                 # Full-res card images (gitignored)
    └── thumbnails/             # Generated WebP thumbnails (gitignored)
```

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/kevin791129/ConanTCG.git
cd ConanTCG
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your database paths and API keys. See [Configuration](#configuration) below.

### 3. Initialize the database

```bash
python scripts/create_database.py
```

### 4. Initialize the AI query log database

```bash
python scripts/create_ai_query_log.py
```

### 5. Set filter sort orders (optional)

Edit `scripts/set_sort_orders.py` to define your preferred order for card types, rarities, and colors, then run:

```bash
python scripts/set_sort_orders.py
```

### 6. Scrape card data

Preview changes before writing to the database:

```bash
python scripts/sync_cards.py --preview
```

Scrape and commit directly:

```bash
python scripts/sync_cards.py
```

### 7. Run the app

```bash
python run.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## Keeping Your Database Up to Date

When new cards are released, re-run the sync script to pull the latest data from the official site. New cards are inserted and changed fields are updated — your collection quantities and watchlist are never touched.

```bash
python scripts/sync_cards.py --preview
```

It is recommended to always use `--preview` first to review what changed before committing.

---

## Configuration

Copy `.env.example` to `.env` and fill in the values:

```bash
# Database
DB_PATH=conan.db
LOG_DB_PATH=query_log.db

# Flask
FLASK_DEBUG=false

# LLM providers — add keys only for the providers you want to use
ANTHROPIC_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
```

---

## AI Query Interface

The `/ai` page lets you query your collection in plain English using an agentic pipeline. Rather than translating your question into a single SQL query, the agent reasons step by step — running multiple queries if needed, inspecting intermediate results, and synthesizing a final natural language answer.

Each query step is shown in the UI with the generated SQL and its results, so you can follow exactly how the agent arrived at its answer.

Example queries:
- *"How many cards do I own in total?"*
- *"Which package am I closest to completing?"*
- *"Do I own more rare or super rare cards?"*
- *"Which blue character cards am I watching?"*

You can choose between supported LLM providers from the dropdown. Query history is stored in a separate log database (`query_log.db`) and never touches your card data.

Supported providers:
- **Anthropic** — Claude Haiku 4.5 (default), Claude Sonnet 4.6
- **Google Gemini** — Gemini 2.0 Flash, Gemini 2.0 Flash Lite, Gemini 2.5 Flash, Gemini 2.5 Pro

---

## Sync Options

| Flag | Description |
|---|---|
| `--preview` | Show changes before committing, prompts for confirmation |
| `--yes` | Auto-confirm commit after preview |
| `--skip-image-download` | Skip downloading card images after sync |
| `--ignore-file FILE` | Path to ignore rules JSON (default: `sync_cards.ignore.json`) |
| `--export-json FILE` | Write change log to a JSON file |
| `--pickle-cards` | Cache scraped data to disk to avoid re-scraping |
| `--unpickle-cards` | Load cached scrape data instead of hitting the site |
| `--db-path PATH` | Path to SQLite database |
| `--verbose` | Enable debug logging |

---

## Ignore Rules

`sync_cards.ignore.json` lets you pin specific field values for cards where the official site has incorrect or inconsistent data. Changes to ignored fields are skipped during sync and logged as warnings.

```json
{
  "rules": [
    {
      "table": "card_base",
      "primary_key": { "name": "card_id", "value": "0584" },
      "field": "categories"
    }
  ]
}
```

Generate a template with:

```bash
python scripts/sync_cards.py --write-ignore-template
```

---

## Data Source

Card data is scraped from the official Takara Tomy card list:
[https://www.takaratomy.co.jp/products/conan-cardgame/cardlist](https://www.takaratomy.co.jp/products/conan-cardgame/cardlist)

This project is a personal tool and is not affiliated with or endorsed by Takara Tomy or the Detective Conan franchise.

---

## Acknowledgements

- UI design prototyped with [Google Stitch](https://stitch.withgoogle.com)
- Card data sourced from the [official Takara Tomy card list](https://www.takaratomy.co.jp/products/conan-cardgame/cardlist)

---

## License

MIT License — see [LICENSE](LICENSE) for details.
