from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any


def _value_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    raise TypeError(f"Unsupported JSON value: {type(value).__name__}")


def _rows(value: Any, path: list[str | int] | None = None):
    path = [] if path is None else path
    value_type = _value_type(value)
    display = "$" if not path else str(path[-1])
    encoded = json.dumps(path, ensure_ascii=False, separators=(",", ":"))
    if value_type in {"object", "array"}:
        yield {"JSON_PATH": encoded, "FIELD": display, "VALUE_TYPE": value_type, "VALUE": ""}
        iterator = value.items() if isinstance(value, dict) else enumerate(value)
        for key, nested in iterator:
            yield from _rows(nested, [*path, key])
    else:
        serialized = "" if value is None else ("true" if value is True else "false" if value is False else str(value))
        yield {"JSON_PATH": encoded, "FIELD": display, "VALUE_TYPE": value_type, "VALUE": serialized}


def json_to_csv(json_path: Path, csv_path: Path) -> None:
    value = json.loads(json_path.read_text(encoding="utf-8"))
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(csv_path) + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["JSON_PATH", "FIELD", "VALUE_TYPE", "VALUE"])
        writer.writeheader()
        writer.writerows(_rows(value))
    temporary.replace(csv_path)


def nice_json_to_csv(json_path: Path, csv_path: Path) -> None:
    """Write a compact, human-oriented leaf-value view of a final artifact."""
    value = json.loads(json_path.read_text(encoding="utf-8"))
    rows = []
    for row in _rows(value):
        if row["VALUE_TYPE"] in {"object", "array"}:
            continue
        path = json.loads(row["JSON_PATH"])
        section = str(path[0]) if path else "$"
        parent = ".".join(f"[{part}]" if isinstance(part, int) else str(part) for part in path[:-1]) or "$"
        rows.append({
            "SECTION": section,
            "ITEM_PATH": parent,
            "FIELD": str(path[-1]) if path else "$",
            "VALUE": row["VALUE"],
            "VALUE_TYPE": row["VALUE_TYPE"],
        })
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(csv_path) + f".{os.getpid()}.tmp")
    with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["SECTION", "ITEM_PATH", "FIELD", "VALUE", "VALUE_TYPE"])
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(csv_path)


def _parse_scalar(value_type: str, value: str) -> Any:
    if value_type == "null":
        return None
    if value_type == "boolean":
        lowered = value.strip().lower()
        if lowered not in {"true", "false"}:
            raise ValueError(f"Boolean CSV value must be true or false, got {value!r}")
        return lowered == "true"
    if value_type == "integer":
        return int(value)
    if value_type == "number":
        return float(value)
    if value_type == "string":
        return value
    if value_type == "object":
        return {}
    if value_type == "array":
        return []
    raise ValueError(f"Unknown VALUE_TYPE: {value_type}")


def _place(root: Any, path: list[str | int], value: Any) -> Any:
    if not path:
        return value
    parent = root
    for index, part in enumerate(path[:-1]):
        next_part = path[index + 1]
        if isinstance(part, int):
            if not isinstance(parent, list):
                raise ValueError(f"JSON path expects an array at {path}")
            while len(parent) <= part:
                parent.append(None)
            if parent[part] is None:
                parent[part] = [] if isinstance(next_part, int) else {}
            parent = parent[part]
        else:
            if not isinstance(parent, dict):
                raise ValueError(f"JSON path expects an object at {path}")
            if part not in parent:
                parent[part] = [] if isinstance(next_part, int) else {}
            parent = parent[part]
    final = path[-1]
    if isinstance(final, int):
        if not isinstance(parent, list):
            raise ValueError(f"JSON path expects an array at {path}")
        while len(parent) <= final:
            parent.append(None)
        parent[final] = value
    else:
        if not isinstance(parent, dict):
            raise ValueError(f"JSON path expects an object at {path}")
        parent[final] = value
    return root


def csv_to_value(csv_path: Path) -> Any:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    required = {"JSON_PATH", "VALUE_TYPE", "VALUE"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError("Companion CSV must contain JSON_PATH, VALUE_TYPE, and VALUE columns")
    decoded = []
    for row in rows:
        path = json.loads(row["JSON_PATH"])
        if not isinstance(path, list) or not all(isinstance(item, (str, int)) for item in path):
            raise ValueError(f"Invalid JSON_PATH: {row['JSON_PATH']}")
        decoded.append((path, _parse_scalar(row["VALUE_TYPE"], row["VALUE"])))
    decoded.sort(key=lambda item: len(item[0]))
    root = None
    for path, value in decoded:
        root = _place(root, path, value)
    return root


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(str(path) + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def mtime_ns(path: Path) -> str:
    return str(path.stat().st_mtime_ns)
