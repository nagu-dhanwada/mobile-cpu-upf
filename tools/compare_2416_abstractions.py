#!/usr/bin/env python3
"""Compare RTL, synthesis-calibrated, and mapped IEEE 2416 power estimates."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


def parse_case(text: str) -> tuple[str, Path]:
    if ":" not in text:
        raise argparse.ArgumentTypeError("case must be LABEL:PATH")
    label, path = text.split(":", 1)
    return label, Path(path)


def xml_escape(text: object) -> str:
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def find_result(path: Path) -> Path:
    if path.is_dir():
        return path / "2416_power_estimate.json"
    return path


def load_rows(cases: list[tuple[str, Path]]) -> list[dict]:
    rows = []
    for label, path in cases:
        result_path = find_result(path)
        data = json.loads(result_path.read_text(encoding="utf-8"))
        rows.append(
            {
                "label": label,
                "path": str(result_path),
                "technology": data.get("technology", ""),
                "scheme": data.get("scheme", ""),
                "duration_ns": float(data.get("duration_ns", 0.0)),
                "total_energy_pj": float(data.get("total_energy_pj", 0.0)),
                "average_power_mw": float(data.get("average_power_mw", 0.0)),
            }
        )
    if rows:
        baseline = rows[0]["total_energy_pj"] or 1.0
        for row in rows:
            row["energy_vs_first"] = row["total_energy_pj"] / baseline
    return rows


def write_csv(path: Path, rows: list[dict]) -> None:
    fields = [
        "label",
        "technology",
        "scheme",
        "duration_ns",
        "total_energy_pj",
        "average_power_mw",
        "energy_vs_first",
        "path",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_svg(path: Path, rows: list[dict]) -> None:
    width = 860
    height = 260
    left = 120
    top = 48
    bar_h = 30
    max_energy = max((row["total_energy_pj"] for row in rows), default=1.0) or 1.0
    plot_w = width - left - 70
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        '<text x="24" y="28" font-family="Arial" font-size="18" font-weight="700">IEEE 2416 Abstraction Comparison</text>',
    ]
    for idx, row in enumerate(rows):
        y = top + idx * (bar_h + 14)
        bar_w = row["total_energy_pj"] / max_energy * plot_w
        lines.append(f'<text x="{left - 10}" y="{y + 20}" text-anchor="end" font-family="Arial" font-size="12">{xml_escape(row["label"])}</text>')
        lines.append(f'<rect x="{left}" y="{y}" width="{bar_w:.2f}" height="{bar_h}" fill="#4c78a8" opacity="0.84"/>')
        lines.append(f'<text x="{left + bar_w + 8:.2f}" y="{y + 20}" font-family="Arial" font-size="12" fill="#444">{row["total_energy_pj"]:.3f} pJ</text>')
    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary(path: Path, rows: list[dict]) -> None:
    lines = [
        "# IEEE 2416 Abstraction Comparison",
        "",
        "| Case | Energy (pJ) | Average Power (mW) | Energy vs First |",
        "| --- | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['label']} | {row['total_energy_pj']:.6f} | "
            f"{row['average_power_mw']:.6f} | {row['energy_vs_first']:.3f}x |"
        )
    lines.extend(
        [
            "",
            "Use this report to explain why each abstraction exists:",
            "",
            "- RTL macro models are fast and architecture-oriented.",
            "- Synthesis-calibrated models adjust macro coefficients using generic Yosys structure.",
            "- Mapped models use Liberty standard cells plus memory macro models and gate-level toggles.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", required=True, type=parse_case)
    parser.add_argument("--out", type=Path, default=Path("reports/legacy2416_compare/abstractions"))
    args = parser.parse_args()

    rows = load_rows(args.case)
    args.out.mkdir(parents=True, exist_ok=True)
    write_csv(args.out / "2416_abstraction_compare.csv", rows)
    write_svg(args.out / "2416_abstraction_compare.svg", rows)
    write_summary(args.out / "2416_abstraction_compare.md", rows)
    print(f"wrote {args.out / '2416_abstraction_compare.md'}")


if __name__ == "__main__":
    main()
