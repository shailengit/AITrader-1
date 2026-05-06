"""Export utilities for cli-anything-tradecraft.

Supports JSON, CSV, and table output formats.
"""

import csv
import json
import sys
from io import StringIO
from typing import Any, Dict, List

from cli_anything.tradecraft.core.config import get_output_format


def render_json(data: Any, pretty: bool = True) -> str:
    indent = 2 if pretty else None
    return json.dumps(data, indent=indent, default=str)


def render_csv(rows: List[Dict[str, Any]]) -> str:
    if not rows:
        return ""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    for row in rows:
        writer.writerow({k: v for k, v in row.items()})
    return output.getvalue()


def render_table(rows: List[Dict[str, Any]], title: str = "") -> str:
    if not rows:
        return f"{title}\nNo data." if title else "No data."

    headers = list(rows[0].keys())
    col_widths = {h: len(h) for h in headers}
    for row in rows:
        for h in headers:
            col_widths[h] = max(col_widths[h], len(str(row.get(h, ""))))

    lines = []
    if title:
        lines.append(title)
        lines.append("=" * len(title))
    separator = " | ".join("-" * (col_widths[h] + 2) for h in headers)
    header_line = " | ".join(f" {h:<{col_widths[h]}} " for h in headers)
    lines.append(header_line)
    lines.append(separator)
    for row in rows:
        line = " | ".join(f" {str(row.get(h, '')):<{col_widths[h]}} " for h in headers)
        lines.append(line)
    return "\n".join(lines)


def emit(data: Any, fmt: str = "", title: str = "") -> None:
    """Emit data to stdout in the configured format."""
    fmt = fmt or get_output_format()
    if fmt == "json":
        print(render_json(data))
    elif fmt == "csv":
        if isinstance(data, list):
            print(render_csv(data))
        else:
            print(render_json(data))
    else:
        if isinstance(data, list):
            print(render_table(data, title=title))
        elif isinstance(data, dict):
            print(render_json(data, pretty=True))
        else:
            print(str(data))
