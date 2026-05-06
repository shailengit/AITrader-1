# cli-anything-tradecraft

A production-ready CLI harness for the TradeCraft trading platform.

## Installation

From the `agent-harness` directory:

```bash
pip install -e .
```

Verify installation:

```bash
which cli-anything-tradecraft
cli-anything-tradecraft --help
```

## Configuration

Set the backend URL (default: `http://localhost:8000`):

```bash
cli-anything-tradecraft config set-url http://localhost:8000
```

Or use an environment variable:

```bash
export TRADECRAFT_BACKEND_URL=http://localhost:8000
```

## Usage

### One-shot commands

```bash
# Health check
cli-anything-tradecraft health

# List sectors
cli-anything-tradecraft sectors list

# Get stocks in a sector
cli-anything-tradecraft sectors stocks xlk

# Run a screener scan
cli-anything-tradecraft screener scan --mode dormant_giant --use-ai

# Run a scan with filters
cli-anything-tradecraft screener scan --mode quant_strategy --filters filters.json

# List locally tracked scans
cli-anything-tradecraft screener list

# Check scan status
cli-anything-tradecraft screener status <scan-id>

# Get scan results
cli-anything-tradecraft screener results <scan-id>

# Get AI analysis report
cli-anything-tradecraft screener ai-report <scan-id>

# Check screener health
cli-anything-tradecraft screener health

# Generate a strategy
cli-anything-tradecraft quantgen generate --prompt "SMA crossover strategy" --tickers AAPL,MSFT

# Run a strategy
cli-anything-tradecraft quantgen run --file strategy.py

# Optimize a strategy
cli-anything-tradecraft quantgen optimize --file strategy.py --params-file params.json

# Run True Walk-Forward Optimization
cli-anything-tradecraft quantgen true-wfo --file strategy.py --params-file params.json

# List saved strategies
cli-anything-tradecraft strategies list
```

### JSON output mode

All commands support `--json` for machine-readable output:

```bash
cli-anything-tradecraft --json sectors list
```

### Interactive REPL

Start the interactive shell:

```bash
cli-anything-tradecraft repl
```

Then type commands without the program name:

```
tradecraft> health
tradecraft> sectors list
tradecraft> screener scan --mode quant_strategy --wait
tradecraft> exit
```

## Project Management

Group related scans and strategies into projects:

```bash
cli-anything-tradecraft projects create momentum-2024
cli-anything-tradecraft screener scan --mode dormant_giant --project momentum-2024
cli-anything-tradecraft projects show momentum-2024

# Add existing scan/strategy to project
cli-anything-tradecraft projects add-scan momentum-2024 <scan-id>
cli-anything-tradecraft projects add-strategy momentum-2024 sma_cross.py

# Set project notes
cli-anything-tradecraft projects notes momentum-2024 --set "Q1 momentum research"
cli-anything-tradecraft projects notes momentum-2024
```

## Command Reference

| Command | Description |
|---------|-------------|
| `health` | Check API and database health |
| `db-status` | Check database connection |
| `sectors list` | List sector ETF performance |
| `sectors stocks <sector>` | Get stocks in sector |
| `sectors ohlcv <ticker>` | Get OHLCV data |
| `screener modes` | List screener modes |
| `screener scan` | Run a scan |
| `screener list` | List locally tracked scans |
| `screener status <id>` | Get scan status |
| `screener results <id>` | Get scan results |
| `screener ai-report <id>` | Get AI analysis report |
| `screener report <id>` | Download PDF report |
| `screener delete <id>` | Delete scan |
| `screener health` | Check screener service health |
| `quantgen generate` | Generate strategy with AI |
| `quantgen run` | Execute strategy |
| `quantgen optimize` | Optimize strategy parameters |
| `quantgen true-wfo` | True Walk-Forward Optimization |
| `quantgen chat` | Chat about code |
| `quantgen indicators` | List indicators |
| `strategies list` | List saved strategies |
| `strategies get <name>` | Get strategy code |
| `strategies save <name>` | Save strategy |
| `strategies delete <name>` | Delete strategy |
| `projects list` | List projects |
| `projects create <name>` | Create project |
| `projects show <name>` | Show project details |
| `projects notes <name>` | Show or set project notes |
| `projects add-scan <name> <id>` | Add scan to project |
| `projects add-strategy <name> <strat>` | Add strategy to project |
| `projects delete <name>` | Delete project |
| `config show` | Show configuration |
| `config set-url <url>` | Set backend URL |
| `config set-format <fmt>` | Set output format |
| `repl` | Interactive REPL |
