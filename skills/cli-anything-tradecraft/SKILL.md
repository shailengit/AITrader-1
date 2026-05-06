---
name: cli-anything-tradecraft
description: CLI harness for TradeCraft trading platform (Sector Rotation, AI Screener, QuantGen)
type: document-skills
---

# cli-anything-tradecraft

A stateful CLI harness for the TradeCraft unified trading platform.

## Commands

### Health
| Command | Description |
|---------|-------------|
| `health` | Check API and database health |
| `db-status` | Check database connection status |

### Sectors
| Command | Description |
|---------|-------------|
| `sectors list` | List sector ETF performance data |
| `sectors stocks <sector>` | Get top stocks within a sector |
| `sectors ohlcv <ticker>` | Get OHLCV data for a ticker |

### Screener
| Command | Description |
|---------|-------------|
| `screener modes` | List available screening modes |
| `screener scan --mode <mode>` | Run a stock screening scan |
| `screener list` | List locally tracked scans |
| `screener status <scan_id>` | Get scan status |
| `screener results <scan_id>` | Get scan results |
| `screener ai-report <scan_id>` | Get AI analysis report |
| `screener report <scan_id>` | Download PDF report |
| `screener delete <scan_id>` | Delete a scan |
| `screener health` | Check screener service health |

### QuantGen
| Command | Description |
|---------|-------------|
| `quantgen generate --prompt "..."` | Generate strategy code with AI |
| `quantgen run --file <file>` | Execute a strategy |
| `quantgen optimize --file <file>` | Optimize strategy parameters |
| `quantgen true-wfo --file <file>` | True Walk-Forward Optimization |
| `quantgen chat --message "..."` | Chat about code with AI |
| `quantgen indicators` | List available indicators |

### Strategies
| Command | Description |
|---------|-------------|
| `strategies list` | List saved strategies |
| `strategies get <name>` | Get strategy code |
| `strategies save <name> --file <file>` | Save a strategy |
| `strategies delete <name>` | Delete a strategy |

### Projects
| Command | Description |
|---------|-------------|
| `projects list` | List local projects |
| `projects create <name>` | Create a project |
| `projects show <name>` | Show project details |
| `projects notes <name>` | Show or set project notes |
| `projects add-scan <name> <scan_id>` | Add scan to project |
| `projects add-strategy <name> <strat>` | Add strategy to project |
| `projects delete <name>` | Delete a project |

### Config
| Command | Description |
|---------|-------------|
| `config show` | Show current configuration |
| `config set-url <url>` | Set backend API URL |
| `config set-format <fmt>` | Set output format (table, json, csv) |

### REPL
| Command | Description |
|---------|-------------|
| `repl` | Start interactive shell |

## Agent Guidance

Use `--json` for all programmatic invocations:

```bash
cli-anything-tradecraft --json sectors list
cli-anything-tradecraft --json screener scan --mode dormant_giant --wait
cli-anything-tradecraft --json quantgen generate --prompt "SMA crossover" --tickers AAPL,MSFT
```

Use `--dry-run` to preview changes without persisting local state.

Backend URL resolution order:
1. `--backend` CLI flag
2. `TRADECRAFT_BACKEND_URL` environment variable
3. `~/.config/cli-anything-tradecraft/config.json`
4. Default: `http://localhost:8000`

State files:
- Config: `~/.config/cli-anything-tradecraft/config.json`
- Session: `~/.config/cli-anything-tradecraft/session.json`
- Projects: `~/.config/cli-anything-tradecraft/projects/*.json`
