# Detective Conan Card Game — Collection Tracker

A full-stack personal collection tracker for the [Detective Conan Trading Card Game](https://www.takaratomy.co.jp/products/conan-cardgame/cardlist). Scrapes card data from the official Takara Tomy site, stores it in a normalized SQLite database, and serves it through a Flask web app with filtering, quantity tracking, and a personal watchlist.

---

## Features

- Scrapes all card data and images from the official card list
- Normalized SQLite database with packages, types, rarities, colors, and categories
- Preview scraped changes before committing to the database
- Field-level ignore rules to override known errors on the official site
- Flask web app with virtual-scrolling card grid
- Per-card quantity tracking and personal watchlist
- Thumbnail generation for fast page loads

---

## Project Structure

```
conan-card-tracker/
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
│   └── routes/
│       ├── collection.py       # Collection and watchlist pages
│       └── api.py              # JSON API endpoints
│
├── scripts/
│   ├── create_database.py      # Initialize the SQLite database
│   ├── sync_cards.py           # Scraper and card importer
│   └── set_sort_orders.py      # Set filter sort orders
│
├── templates/
│   ├── base.html
│   ├── collection.html
│   └── watchlist.html
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

Edit `.env` if you want a custom database path.

### 3. Initialize the database

```bash
python scripts/create_database.py
```

### 4. Set filter sort orders (optional)

Edit `scripts/set_sort_orders.py` to define your preferred order for card types, rarities, and colors, then run:

```bash
python scripts/set_sort_orders.py
```

### 5. Scrape card data

Preview changes before writing to the database:

```bash
python scripts/sync_cards.py --preview
```

Scrape and commit directly:

```bash
python scripts/sync_cards.py
```

### 6. Run the app

```bash
python run.py
```

Open [http://localhost:5000](http://localhost:5000) in your browser.

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

## License

MIT License — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

- UI design prototyped with [Google Stitch](https://stitch.google.com)
- Card data sourced from the [official Takara Tomy card list](https://www.takaratomy.co.jp/products/conan-cardgame/cardlist)
