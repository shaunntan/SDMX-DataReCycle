from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup

from .config import STANDARD_CACHE

TARGETS = [
    "https://registry.sdmx.org/items/codelist.html",
    "https://unstats.un.org/unsd/methodology/m49/",
    "https://sdmx.org/wp-content/uploads/SDMx_Glossary_Version_2_1_December_2020.htm",
]


def authoritative_evidence(refresh: bool = False) -> str:
    """Cache small, credential-free snapshots from official sources for agent evidence."""
    STANDARD_CACHE.mkdir(parents=True, exist_ok=True)
    records = []
    for index, url in enumerate(TARGETS, 1):
        cache = STANDARD_CACHE / f"source_{index}.json"
        if cache.exists() and not refresh:
            try:
                records.append(json.loads(cache.read_text(encoding="utf-8")))
                continue
            except (OSError, json.JSONDecodeError):
                pass
        record = {"url": url, "checked_at": datetime.now(timezone.utc).isoformat(), "status": "UNAVAILABLE", "text_excerpt": ""}
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 SDMX research pipeline"})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw = response.read(2_000_000)
                content_type = response.headers.get("Content-Type", "")
            if "html" in content_type.lower() or raw.lstrip().startswith(b"<"):
                visible = BeautifulSoup(raw, "lxml").get_text(" ", strip=True)
                visible = re.sub(r"\s+", " ", visible)
                terms = ("frequency", "sex", "France", "Germany", "Thailand", "observation status", "codelist")
                excerpts = []
                for term in terms:
                    match = re.search(re.escape(term), visible, re.I)
                    if match:
                        excerpts.append(visible[max(0, match.start() - 250):match.end() + 500])
                record["text_excerpt"] = " ... ".join(excerpts)[:6000] or visible[:3000]
                record["status"] = "FETCHED"
            else:
                record["status"] = "BINARY_NOT_INCLUDED"
        except Exception as error:
            record["error_type"] = type(error).__name__
        cache.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(record)
    return "\n\n".join(
        f"OFFICIAL SOURCE: {item['url']}\nCHECK STATUS: {item['status']}\nEVIDENCE EXCERPT: {item.get('text_excerpt') or 'No online excerpt available; do not claim confirmation from this source.'}"
        for item in records
    )

