# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
python social-pulse.py              # Collect + format, write to social-pulse.json
python social-pulse.py --dry        # Show output to stdout, skip file writes
```

## Architecture

Single-file Python script (`social-pulse.py`) — a 24-hour social media aggregator that collects trending topics from PTT, Reddit, and web sources, deduplicates, and outputs formatted reports.

### Data Flow

1. **PTT** — Firecrawl scrapes `pttweb.cc/hot/all/today` → markdown → regex parse
2. **Reddit r/taiwan** — Firecrawl scrapes `old.reddit.com/r/taiwan/hot/` → markdown → regex parse
3. **Reddit AI agent** — Direct Reddit JSON API search for "AI agent Taiwan" keyword
4. **Web trending** — Firecrawl Google site-search for Threads/Facebook/Instagram (best-effort, often empty)
5. **Deduplication** — URL root + title prefix matching
6. **Output** — Discord-formatted text (stdout) + JSON (script dir + Obsidian vault staging)

### Key Components

| Function | Purpose |
|---|---|
| `fetch_firecrawl()` | POST to local Firecrawl instance (`192.168.1.11:3002`) for markdown scraping |
| `parse_ptt_from_markdown()` | Regex-parse Firecrawl markdown into structured items |
| `parse_reddit_from_markdown()` | Regex-parse Reddit Firecrawl markdown into structured items |
| `fetch_reddit_ai_query()` | Direct Reddit JSON API search (no Firecrawl needed) |
| `fetch_web_trending()` | Google site-search via Firecrawl for social platform trends |
| `deduplicate()` | Remove near-duplicates by URL root + title prefix |
| `format_discord()` | Format items into Discord-friendly plain text with source sections |
| `run()` | Orchestrator: fetch all sources → dedup → write JSON → print Discord text |

### Output Items Structure

Each item is a dict: `{"title": "...", "url": "...", "source": "ptt|reddit|reddit_ai|web", "meta": "..."}`

### Output Files

- `social-pulse.json` — Script directory, for debugging and cron inspection
- `vault/50_Outputs/staging/social-pulse.json` — For Obsidian content-researcher skill to pick up as topic research material

### Dependencies

- **Firecrawl** (local instance at `192.168.1.11:3002`) — PTT & Reddit & web scraping
- **Python stdlib** — `requests` for HTTP, `urllib.parse` for URL encoding, `datetime` for timestamps
- No `requirements.txt` — single file, `pip install requests` if missing

### Platform Compatibility

Vault staging path auto-fallback: Windows (`C:/Users/.../iCloudDrive/...`) → macOS (`~/Library/Mobile Documents/...`).

### Cron Schedule

Runs daily at 07:00 Taipei Time (UTC+8) via Hermes cron. Output feeds into:
- Discord Home channel (plain text daily briefing via stdout)
- content-researcher skill (JSON from vault staging for topic selection)
