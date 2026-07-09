"""HTTP API client for the TradeCraft backend.
"""

import json
import urllib.parse
import urllib.request
import urllib.error
from typing import Any, Dict, Optional

from cli_anything.tradecraft.core.config import get_backend_url, get_timeout


class APIError(Exception):
    def __init__(self, message: str, status: int = 0, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


def _request(
    method: str,
    path: str,
    body: Optional[Dict[str, Any]] = None,
    timeout: Optional[int] = None,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    base = get_backend_url()
    if params:
        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in path else "?"
        path = f"{path}{separator}{query}"
    url = f"{base}{path}"
    req_headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if headers:
        req_headers.update(headers)

    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    try:
        resp = urllib.request.urlopen(req, timeout=timeout or get_timeout())
        raw = resp.read().decode("utf-8")
        if not raw:
            return {}
        return json.loads(raw)
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8") if e.fp else ""
        raise APIError(f"HTTP {e.code}: {e.reason}", status=e.code, body=body_text)
    except urllib.error.URLError as e:
        raise APIError(f"Connection failed: {e.reason}", status=0)
    except json.JSONDecodeError as e:
        raise APIError(f"Invalid JSON response: {e}", status=0)


def get(path: str, **kwargs) -> Dict[str, Any]:
    return _request("GET", path, **kwargs)


def post(path: str, body: Dict[str, Any], **kwargs) -> Dict[str, Any]:
    return _request("POST", path, body=body, **kwargs)


def delete(path: str, **kwargs) -> Dict[str, Any]:
    return _request("DELETE", path, **kwargs)
