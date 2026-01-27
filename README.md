# Weekly Deal & Partner Report

Local Python automation that aggregates data from Google Calendar, Gmail, and Granola notes to generate structured weekly reports using a local LLM (Gemma 2 via Ollama).

## Prerequisites

- Python 3.10+
- Ollama with gemma2:27b model
- Google Cloud project with API access

### Ollama setup

1. Install Ollama: https://ollama.ai
2. Pull the model:
   ```bash
   ollama pull gemma2:27b
   ```
3. Start Ollama:
   ```bash
   ollama serve
   ```

## Installation

1. Clone or download this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Set up Google API access:
   ```bash
   python setup_google_auth.py
   ```

## Configuration

### config/settings.json

```json
{
  "granola_path": "~/Google Drive/Granola Dumps/Sales/",
  "ollama_endpoint": "http://localhost:11434/api/generate",
  "ollama_model": "gemma2:27b",
  "output_folder_id": "",
  "lookback_days": 7,
  "internal_domain": "folloze.com"
}
```

- `granola_path`: Local folder containing Granola meeting notes
- `output_folder_id`: Google Drive folder ID for saving reports (optional)
- `lookback_days`: Number of days to look back for activity
- `internal_domain`: Your company's email domain (filtered out)

### config/partners.json

Add your agency and tech partners:

```json
{
  "agency_partners": [
    {"domain": "agency.com", "name": "Agency Name"}
  ],
  "tech_partners": [
    {"domain": "techpartner.com", "name": "Tech Partner Name"}
  ]
}
```

### config/active_deals.json

Active deals are managed through the interview process or manually:

```json
[
  {"domain": "prospect.com", "name": "Prospect Company", "added": "2025-01-20"}
]
```

## Usage

Run the full workflow:

```bash
python weekly_report.py
```

### Options

- `--skip-interview`: Skip the deal classification interview
- `--markdown-only`: Generate Markdown file instead of Google Doc
- `--no-commit`: Skip git commit after completion

### Workflow

1. **Interview**: Scans calendar for new external domains and prompts you to classify them as deals
2. **Data collection**: Fetches calendar events, matches Granola notes, retrieves Gmail threads
3. **Synthesis**: Sends context to Ollama for AI summarization
4. **Report generation**: Creates a Google Doc (or Markdown file)
5. **Git commit**: Commits config changes

## File structure

```
weekly-report/
├── config/
│   ├── active_deals.json    # Active deals (managed via interview)
│   ├── partners.json        # Agency and tech partners
│   └── settings.json        # Application settings
├── src/
│   ├── google_calendar.py   # Calendar API client
│   ├── gmail_client.py      # Gmail API client
│   ├── granola_scanner.py   # Local notes scanner
│   ├── ollama_client.py     # Ollama LLM interface
│   ├── report_generator.py  # Google Docs/Markdown output
│   └── interview.py         # Human-in-the-loop setup
├── logs/                    # Runtime logs and markdown reports
├── setup_google_auth.py     # Google OAuth setup
├── weekly_report.py         # Main entry point
└── requirements.txt
```

## Granola notes format

Notes should be saved as text files with this naming pattern:

```
YYYY-MM-DD_CompanyName_Topic.txt
```

Example: `2025-01-20_AcmeCorp_Discovery-Call.txt`

## Calendar filtering

The following events are excluded:
- Purple (Personal) - colorId: 1
- Orange (Admin) - colorId: 6
- Grey (Blocks) - colorId: 8
- Internal-only meetings (all attendees from your domain)

## Report output

The generated report includes:

- **Deal Updates**: Activity, deal status, risks, and action items for each deal
- **Agency Partner Updates**: Summary of agency partner interactions
- **Tech Alliance Updates**: Summary of tech partner interactions
