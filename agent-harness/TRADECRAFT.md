# TRADECRAFT.md

## Software: TradeCraft

TradeCraft is a unified trading platform combining three tools:
1. **Sector Rotation Scanner** - Analyze sector ETF momentum and find leading stocks
2. **AI Stock Screener** - Multi-agent technical and fundamental stock screening
3. **QuantGen Strategy Builder** - AI-powered quantitative strategy generation with VectorBT

## Architecture

- **Backend**: FastAPI (Python) on port 8000
- **Frontend**: React + TypeScript + Tailwind CSS (Vite dev server)
- **Database**: PostgreSQL (`sp1500_1d`)
- **API Prefix**: `/api`

## API Mapping

### Health
- `GET /api/health` - API health check
- `GET /api/db-status` - Database status

### Sector Rotation
- `GET /api/sectors` - List sector performance
- `GET /api/stocks/{sector}` - Get stocks in sector
- `GET /api/ohlcv/{ticker}` - Get OHLCV data

### AI Stock Screener
- `GET /api/screener/modes` - List modes
- `POST /api/screener/scan` - Start scan (async)
- `GET /api/screener/status/{scan_id}` - Polling status
- `GET /api/screener/results/{scan_id}` - Final results
- `GET /api/screener/ai-report/{scan_id}` - AI report text
- `GET /api/screener/report/{scan_id}` - PDF report
- `DELETE /api/screener/scan/{scan_id}` - Delete scan
- `GET /api/screener/stream/{scan_id}` - SSE real-time stream
- `GET /api/screener/health` - Screener service health

### QuantGen Strategy Builder
- `GET /api/health` (quantgen health)
- `POST /api/generate` - Generate strategy code
- `POST /api/run` - Execute strategy
- `POST /api/optimize` - Parameter optimization
- `POST /api/true-wfo` - True Walk-Forward Optimization (deprecated)
- `POST /api/chat` - Chat about code
- `GET /api/strategies` - List saved strategies
- `POST /api/strategies` - Save strategy
- `GET /api/strategies/{name}` - Load strategy
- `DELETE /api/strategies/{name}` - Delete strategy
- `GET /api/indicators` - List technical indicators

## CLI Design

### Command Groups
1. `health` / `db-status` - System health checks
2. `sectors` - Sector rotation analysis
3. `screener` - AI stock screening (scan, list, status, results, ai-report, report, delete, health)
4. `quantgen` - Strategy generation and execution (generate, run, optimize, true-wfo, chat, indicators)
5. `strategies` - Strategy file management
6. `projects` - Local project grouping (create, show, notes, add-scan, add-strategy, delete)
7. `config` - CLI configuration
8. `repl` - Interactive shell

### State Model
- **Config**: `~/.config/cli-anything-tradecraft/config.json`
  - `backend_url`: API base URL
  - `output_format`: `table` | `json` | `csv`
  - `timeout`: Request timeout
- **Session**: `~/.config/cli-anything-tradecraft/session.json`
  - `scans`: Active scan IDs with metadata
  - `strategies`: Recently used strategies
- **Projects**: `~/.config/cli-anything-tradecraft/projects/*.json`
  - Group scans and strategies by research theme

### Output Formats
- `--json`: Raw JSON for agent consumption
- Table: Human-readable aligned columns
- CSV: Comma-separated values

### Auto-Save Behavior
Session-based commands (scans, projects) auto-save to `session.json`.
Use `--dry-run` to suppress persistence.

## Agent Guidance

- Use `--json` when chaining commands or parsing output programmatically.
- Use `--wait` with `screener scan` to block until completion.
- Use `--filters <file.json>` with `screener scan` for advanced filtering.
- Use `screener list` to see your scan history without remembering IDs.
- Use `screener ai-report <id>` to fetch the AI analysis after a `--use-ai` scan.
- Associate scans with `--project` for later grouping, or use `projects add-scan` afterward.
- Use `projects notes <name>` to keep research context alongside scans and strategies.
- Strategy files are Python code; pass them via `--file`.
- The backend must be running before CLI commands work.
