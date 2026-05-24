#!/usr/bin/env python3
"""Generate visual comparison reports from IEEE 2416 power estimate results."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


COLORS = ["#4c78a8", "#f58518", "#54a24b", "#e45756", "#72b7b2", "#b279a2", "#ff9da6", "#9d755d"]


def xml_escape(text: object) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def load_result(path: Path, label: str) -> dict:
    result = json.loads(path.read_text(encoding="utf-8"))
    return {
        "label": label,
        "path": str(path),
        "technology": result.get("technology", ""),
        "scheme": result.get("scheme", ""),
        "duration_ns": result.get("duration_ns", 0.0),
        "total_energy_pj": result.get("total_energy_pj", 0.0),
        "average_power_mw": result.get("average_power_mw", 0.0),
        "domains": {row["domain"]: row for row in result.get("domains", [])},
        "blocks": {row["block"]: row for row in result.get("blocks", [])},
    }


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_bar_svg(path: Path, rows: list[dict], value_key: str, title: str) -> None:
    width = 980
    height = 390
    left = 84
    right = 28
    top = 54
    bottom = 86
    plot_width = width - left - right
    plot_height = height - top - bottom
    max_value = max((float(row[value_key]) for row in rows), default=1.0) or 1.0
    bar_gap = 18
    bar_width = max(28, (plot_width - bar_gap * (len(rows) + 1)) / max(len(rows), 1))

    def y(value: float) -> float:
        return top + plot_height - (value / max_value) * plot_height

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="24" y="30" font-family="Arial" font-size="18" font-weight="700">{xml_escape(title)}</text>',
    ]
    for i in range(5):
        value = max_value * i / 4
        yy = y(value)
        lines.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width - right}" y2="{yy:.2f}" stroke="#e4e7eb"/>')
        lines.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" font-family="Arial" font-size="11" fill="#555">{value:.2f}</text>')
    lines.append(f'<line x1="{left}" y1="{top + plot_height}" x2="{width - right}" y2="{top + plot_height}" stroke="#222"/>')
    lines.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_height}" stroke="#222"/>')

    for idx, row in enumerate(rows):
        value = float(row[value_key])
        x0 = left + bar_gap + idx * (bar_width + bar_gap)
        y0 = y(value)
        color = COLORS[idx % len(COLORS)]
        lines.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{bar_width:.2f}" height="{top + plot_height - y0:.2f}" fill="{color}" opacity="0.88"/>')
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{y0 - 6:.2f}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333">{value:.3f}</text>')
        label = row["label"]
        lines.append(f'<text x="{x0 + bar_width / 2:.2f}" y="{top + plot_height + 20}" text-anchor="middle" font-family="Arial" font-size="11" fill="#333" transform="rotate(25 {x0 + bar_width / 2:.2f} {top + plot_height + 20})">{xml_escape(label)}</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(path: Path, rows: list[dict], title: str) -> None:
    lines = [
        f"# {title}",
        "",
        "| Case | Technology | Scheme | Energy (pJ) | Average Power (mW) | Duration (ns) |",
        "| --- | --- | --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['technology']} | {row['scheme']} | "
            f"{row['total_energy_pj']:.6f} | {row['average_power_mw']:.6f} | {row['duration_ns']:.3f} |"
        )
    lines.extend(
        [
            "",
            "Generated from IEEE 2416 XML macro model estimates.",
            "",
            "- Energy chart: `2416_compare_energy.svg`",
            "- Average power chart: `2416_compare_average_power.svg`",
            "- Raw comparison table: `2416_compare.csv`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def result_path(root: Path, label: str, prefix: str, suffix: str) -> Path:
    return root / f"{prefix}{label}{suffix}" / "2416_power_estimate.json"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, default=Path("reports/2416"))
    parser.add_argument("--labels", nargs="+", required=True)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--suffix", default="")
    parser.add_argument("--title", default="IEEE 2416 Power Comparison")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    rows = []
    for label in args.labels:
        rows.append(load_result(result_path(args.result_root, label, args.prefix, args.suffix), label))

    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(
        args.out / "2416_compare.csv",
        rows,
        ["label", "technology", "scheme", "duration_ns", "total_energy_pj", "average_power_mw", "path"],
    )
    write_summary(args.out / "2416_compare_summary.md", rows, args.title)
    write_bar_svg(args.out / "2416_compare_energy.svg", rows, "total_energy_pj", f"{args.title}: Energy")
    write_bar_svg(args.out / "2416_compare_average_power.svg", rows, "average_power_mw", f"{args.title}: Average Power")
    print(f"wrote {args.out / '2416_compare_summary.md'}")


if __name__ == "__main__":
    main()
