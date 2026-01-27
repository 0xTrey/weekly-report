# Weekly Deal & Partner Report

Automated weekly report generator that aggregates data from Google Calendar, Gmail, and meeting notes (Google Drive) to produce executive summaries using a local LLM.

## Features

- Scans Google Calendar for external meetings (filters out internal, personal, admin events)
- Retrieves email threads with deals and partners from Gmail
- Matches meetings with notes stored in Google Drive
- Synthesizes updates using local Ollama (Gemma 3) for privacy
- Generates formatted Google Docs or Markdown reports
- Human-in-the-loop deal classification from calendar contacts

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ Google Calendar │     │     Gmail       │     │  Google Drive   │
│   (meetings)    │     │   (threads)     │     │ (meeting notes) │
└────────┬────────┘     └────────┬────────┘     └────────┬────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │   Data Collection &    │
                    │      Matching          │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   Ollama (Gemma 3)     │
                    │   Local Synthesis      │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   Google Docs Report   │
                    └────────────────────────┘
```

## Prerequisites

- Python 3.9+
- [Ollama](https://ollama.ai) with gemma3:27b model
- Google Cloud project with OAuth credentials

### Install Ollama and model

```bash
# Install Ollama (macOS)
brew install ollama

# Or download from https://ollama.ai

# Pull the model (~17GB)
ollama pull gemma3:27b

# Start Ollama server
ollama serve
```

## Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/weekly-report.git
cd weekly-report

# Install dependencies
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
  "granola_folder_id": "YOUR_GOOGLE_DRIVE_FOLDER_ID",
  "ollama_endpoint": "http://localhost:11434/api/generate",
  "ollama_model": "gemma3:27b",
  "output_folder_id": "",
  "lookback_days": 7,
  "internal_domain": "yourcompany.com"
}
```

| Setting | Description |
|---------|-------------|
| `granola_folder_id` | Google Drive folder ID containing meeting notes |
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

## Usage

### Full workflow

```bash
python weekly_report.py
```

This will:
1. Interview you about new external domains from calendar
2. Collect calendar, email, and notes data
3. Synthesize summaries via Ollama
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

## Meeting notes format

Notes in the Google Drive folder can be:

1. **Google Docs** with date headers like "January 27, 2026"
2. **Text files** named `YYYY-MM-DD_CompanyName_Topic.txt`

The scanner matches notes to calendar meetings by date and company name.

## Report output

Generated reports include:

- **Deal Updates**: Activity, status, risks, action items
- **Agency Partner Updates**: Partner interaction summaries
- **Tech Alliance Updates**: Tech partner summaries

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
│   ├── granola_scanner.py   # Drive notes scanner
│   ├── ollama_client.py     # Ollama LLM interface
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

**Never commit:**
- `credentials.json`
- `token.json`
- `.env` files

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request
