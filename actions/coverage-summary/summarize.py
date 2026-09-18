#!/usr/bin/env python3
"""Render an lcov.info report as a Markdown summary for the GitHub job summary.

Visibility only: never fails the build. A missing or empty report prints a
warning section instead. Usage: summarize.py <lcov.info> <title> [workspace]
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

WEAKEST_DIRS = 10
MIN_DIR_LINES = 20


def parse(text):
    """Yield one dict per source file: path, lf, lh, brf, brh, fnf, fnh."""
    record = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("SF:"):
            record = {"path": line[3:], "lf": 0, "lh": 0, "brf": 0, "brh": 0, "fnf": 0, "fnh": 0}
        elif record is not None and ":" in line:
            key, _, value = line.partition(":")
            if key in ("LF", "LH", "BRF", "BRH", "FNF", "FNH") and value.isdigit():
                record[key.lower()] = int(value)
        elif line == "end_of_record" and record is not None:
            yield record
            record = None


def relative(path, workspace):
    """Workspace-relative path; paths outside the workspace are kept as they are."""
    if not os.path.isabs(path):
        return path[2:] if path.startswith("./") else path
    try:
        return str(Path(path).resolve().relative_to(Path(workspace).resolve()))
    except (ValueError, OSError):
        return path


def pct(hit, found):
    return "—" if not found else f"{100 * hit / found:.1f}%"


def directory(path, depth=2):
    parts = Path(path).parts[:-1]
    return "/".join(parts[:depth]) or "."


def render(files, title):
    if not files:
        return f"### {title}\n\n⚠️ Coverage raporunda hiç dosya yok (lcov boş).\n"
    total = defaultdict(int)
    by_dir = defaultdict(lambda: defaultdict(int))
    for f in files:
        for key in ("lf", "lh", "brf", "brh", "fnf", "fnh"):
            total[key] += f[key]
            by_dir[directory(f["path"])][key] += f[key]
        by_dir[directory(f["path"])]["files"] += 1
    out = [
        f"### {title}",
        "",
        "| | Kapsanan | Toplam | Oran |",
        "|---|---:|---:|---:|",
        f"| Satır | {total['lh']} | {total['lf']} | **{pct(total['lh'], total['lf'])}** |",
        f"| Dal (branch) | {total['brh']} | {total['brf']} | {pct(total['brh'], total['brf'])} |",
        f"| Fonksiyon | {total['fnh']} | {total['fnf']} | {pct(total['fnh'], total['fnf'])} |",
        "",
        f"{len(files)} dosya ölçüldü. Bu tablo yalnız görünürlük içindir; eşik yok.",
    ]
    weak = sorted(((d, v) for d, v in by_dir.items() if v["lf"] >= MIN_DIR_LINES),
                  key=lambda item: item[1]["lh"] / item[1]["lf"])[:WEAKEST_DIRS]
    if weak:
        out += ["", f"<details><summary>En zayıf {len(weak)} klasör (en az {MIN_DIR_LINES} satır)</summary>", "",
                "| Klasör | Dosya | Satır oranı | Kapsanmayan satır |", "|---|---:|---:|---:|"]
        out += [f"| `{d}` | {v['files']} | {pct(v['lh'], v['lf'])} | {v['lf'] - v['lh']} |" for d, v in weak]
        out += ["", "</details>"]
    return "\n".join(out) + "\n"


def main(argv):
    if len(argv) < 3:
        print("usage: summarize.py <lcov.info> <title> [workspace]", file=sys.stderr)
        return 0
    lcov, title = Path(argv[1]), argv[2]
    workspace = argv[3] if len(argv) > 3 else os.environ.get("GITHUB_WORKSPACE", os.getcwd())
    if not lcov.is_file():
        print(f"### {title}\n\n⚠️ `{lcov}` bulunamadı; coverage raporu üretilmemiş.\n")
        return 0
    files = [dict(f, path=relative(f["path"], workspace)) for f in parse(lcov.read_text(errors="replace"))]
    print(render(files, title))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
