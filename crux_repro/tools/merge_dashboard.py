#!/usr/bin/env python3
"""Merge data.json into dashboard.html to produce a fully self-contained HTML file.

Usage:
  python3 tools/merge_dashboard.py \
    --html vis/dashboard.html \
    --data results/web_dashboard/data.json \
    --out results/web_dashboard/dashboard.html
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge data.json into dashboard.html")
    parser.add_argument("--html", type=Path, required=True)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    html = args.html.read_text(encoding="utf-8")
    data = json.loads(args.data.read_text(encoding="utf-8"))

    # Replace the loadData() function with one that uses embedded data
    # Old pattern: fetch('data.json')
    # New pattern: const EMBEDDED_DATA = {...}; DATA = EMBEDDED_DATA; init();
    embedded_json = json.dumps(data, indent=2, ensure_ascii=False)

    # Find the loadData function and replace it
    old_load = """async function loadData() {
  try {
    const resp = await fetch('data.json');
    DATA = await resp.json();
    init();
  } catch(e) {
    document.body.innerHTML = `<div style="padding:40px;text-align:center"><h2>数据加载失败</h2><p>${e.message}</p><p>请确保 data.json 与本文件在同一目录</p></div>`;
  }
}"""

    new_load = f"""function loadData() {{
  const EMBEDDED_DATA = {embedded_json};
  DATA = EMBEDDED_DATA;
  init();
}}"""

    html = html.replace(old_load, new_load)

    # Also replace the auto-play initial load
    # window.addEventListener('DOMContentLoaded', loadData); stays the same

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html, encoding="utf-8")
    print(f"Merged: {args.out} ({args.out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
