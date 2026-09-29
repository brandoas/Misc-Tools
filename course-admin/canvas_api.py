"""Shared Canvas API helper for Canvas-Tools.

Reads credentials from the .env file in this directory. Either naming
convention works:

    ACCESS_TOKEN = "24063~..."          (legacy Canvas-Tools style)
    API_URL = "https://ohio.instructure.com/api/graphql"

or

    CANVAS_API_TOKEN=24063~...          (ITS-4750-Infrastructure style)
    CANVAS_BASE_URL=https://ohio.instructure.com

Never commit the .env file.
"""

import os
import sys
from urllib.parse import urlsplit

import requests
from dotenv import load_dotenv

def _find_env():
    """Look for .env in this directory, then each parent (so the repo-root
    .env serves every subfolder)."""
    d = os.path.dirname(os.path.abspath(__file__))
    while True:
        candidate = os.path.join(d, ".env")
        if os.path.isfile(candidate):
            return candidate
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


load_dotenv(_find_env())

TOKEN = os.getenv("CANVAS_API_TOKEN") or os.getenv("ACCESS_TOKEN")
_url = os.getenv("CANVAS_BASE_URL") or os.getenv("API_URL") or "https://ohio.instructure.com"
_parts = urlsplit(_url)
BASE_URL = f"{_parts.scheme}://{_parts.netloc}"

if not TOKEN:
    sys.exit("No Canvas token found. Put ACCESS_TOKEN (or CANVAS_API_TOKEN) in .env.")

HEADERS = {"Authorization": f"Bearer {TOKEN}"}
_session = requests.Session()
_session.headers.update(HEADERS)


def get(path, params=None):
    """GET a single REST resource, e.g. get('/api/v1/courses/12345')."""
    r = _session.get(f"{BASE_URL}{path}", params=params or {})
    r.raise_for_status()
    return r.json()


def get_paginated(path, params=None):
    """GET a REST collection, following Canvas Link-header pagination."""
    results = []
    params = dict(params or {})
    params.setdefault("per_page", 100)
    url = f"{BASE_URL}{path}"
    while url:
        r = _session.get(url, params=params)
        r.raise_for_status()
        results.extend(r.json())
        url = r.links.get("next", {}).get("url")
        params = {}  # the next-page URL already carries the query string
    return results


def put(path, data):
    """PUT form-encoded data to a REST resource."""
    r = _session.put(f"{BASE_URL}{path}", data=data)
    r.raise_for_status()
    return r.json()


def graphql(query, variables=None):
    """POST a GraphQL query to /api/graphql."""
    r = _session.post(
        f"{BASE_URL}/api/graphql",
        headers={"Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
    )
    r.raise_for_status()
    return r.json()
