# Weekly Deal & Partner Report

Automated weekly report generator that aggregates data from Google Calendar, Gmail, and Granola meeting notes to produce executive summaries using a local LLM.

## Features

- Scans Google Calendar for external meetings (filters out internal, personal, admin events)
- Retrieves email threads with deals and partners from Gmail
- Matches meetings with Granola notes from the local cache (by calendar event ID)
- Synthesizes updates using LLMGateway (local Ollama, falls back to cloud)
- Generates formatted Google Docs or Markdown reports
- Human-in-the-loop deal classification from calendar contacts

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Google Calendar │     │     Gmail       │     │  Granola Cache  │
│   (meetings)    │     │   (threads)     │     │ (notes/panels)  │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Data Collection &    │
                    │   Calendar ID Matching │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   LLMGateway           │
                    │   (local -> cloud)     │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   Google Docs Report   │
                    └────────────────────────┘
```

## Prerequisites

- Python 3.10+
- [Ollama](https://ollama.ai) with a supported model (e.g. gemma3:27b)
- Google Cloud project with OAuth credentials
- [Granola](https://granola.so) installed (provides local meeting cache)
- `granola-reader` package installed (`pip install -e ~/Projects/granola-reader`)

### Install Ollama and model

```bash
brew install ollama
ollama pull gemma3:27b
ollama serve
```

## Installation

```bash
git clone https://github.com/0xTrey/weekly-report.git
cd weekly-report
pip install -r requirements.txt

# Set up Google API credentials
python setup_google_auth.py
```

### Google Cloud setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select existing)
3. Enable these APIs:
   - Google Calendar API
   - Gmail API
   - Google Docs API
   - Google Drive API
4. Go to "APIs & Services" > "Credentials"
5. Create OAuth 2.0 Client ID (Desktop application)
6. Download JSON and save as `credentials.json` in project root
7. Run `python setup_google_auth.py` to complete OAuth flow

## Configuration

### config/settings.json

```json
{
  "ollama_endpoint": "http://localhost:11434/api/generate",
  "ollama_model": "gemma3:27b",
  "output_folder_id": "",
  "lookback_days": 7,
  "internal_domain": "yourcompany.com"
}
```

| Setting | Description |
|---------|-------------|
| `ollama_model` | Ollama model to use for synthesis |
| `output_folder_id` | Drive folder for generated reports (optional) |
| `lookback_days` | Days to look back for activity |
| `internal_domain` | Your company domain (filtered from external meetings) |

### config/partners.json

```json
{
  "agency_partners": [
    {"domain": "agency.com", "name": "Agency Name"}
  ],
  "tech_partners": [
    {"domain": "techpartner.com", "name": "Tech Partner"}
  ]
}
```

### config/active_deals.json

Managed via the interview process or manually:

```json
[
  {"domain": "prospect.com", "name": "Prospect Corp", "added": "2026-01-20"}
]
```

## Meeting notes (Granola)

Meeting notes come from Granola's local Electron cache at `~/Library/Application Support/Granola/cache-v3.json`. The scanner matches Granola documents to calendar meetings by Google Calendar event ID (primary) with a date+title fallback.

Content priority:
1. Panel content (AI-generated structured summaries from Granola)
2. User's typed notes in markdown
3. Plain text notes

This replaced the earlier Google Drive-based approach which required exporting notes to Drive and fuzzy-matching on filenames. The local cache is faster, more reliable, and provides richer data (panels, transcripts, attendees).

## Usage

### Full workflow

```bash
python weekly_report.py
```

This will:
1. Interview you about new external domains from calendar
2. Collect calendar, email, and Granola data
3. Synthesize summaries via LLMGateway
4. Generate a Google Doc report

### Options

```bash
python weekly_report.py --help

Options:
  --skip-interview   Skip the deal classification interview
  --markdown-only    Generate Markdown instead of Google Doc
  --no-commit        Skip git commit after completion
  --dry-run          Validate config without generating report
```

### Dry run (recommended first)

```bash
python weekly_report.py --dry-run
```

## Calendar color filtering

Events with these colors are excluded:

| Color | Google colorId | Purpose |
|-------|----------------|---------|
| Lavender | 1 | Internal meetings |
| Grape | 3 | Personal |
| Tangerine | 6 | Admin |
| Graphite | 8 | Calendar blocks |

Customize in `src/google_calendar.py` if your color scheme differs.

## Report output

Generated reports include:

- Deal updates: activity, status, risks, action items
- Agency partner updates: partner interaction summaries
- Tech alliance updates: tech partner summaries

## Project structure

```
weekly-report/
├── config/
│   ├── active_deals.json    # Active deals (via interview)
│   ├── partners.json        # Agency and tech partners
│   └── settings.json        # Application settings
├── src/
│   ├── google_calendar.py   # Calendar API client
│   ├── gmail_client.py      # Gmail API client
│   ├── granola_scanner.py   # Local Granola cache scanner
│   ├── ollama_client.py     # LLMGateway interface
│   ├── report_generator.py  # Report output
│   └── interview.py         # Deal classification
├── logs/                    # Markdown reports
├── setup_google_auth.py     # OAuth setup
├── weekly_report.py         # Main entry point
├── requirements.txt
├── SECURITY.md              # Security guidelines
└── README.md
```

## Security

See [SECURITY.md](SECURITY.md) for handling credentials.

Never commit: `credentials.json`, `token.json`, `.env` files.

## License

MIT
