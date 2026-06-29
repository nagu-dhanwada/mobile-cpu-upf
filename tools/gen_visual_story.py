#!/usr/bin/env python3
"""Generate a self-contained visual dashboard for mobile CPU power exploration."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path
from typing import Any


STATE_COLORS = {
    "RUN": "#2f80ed",
    "IDLE": "#56cc9d",
    "LIGHT_SLEEP": "#f2c94c",
    "DEEP_SLEEP": "#9b51e0",
    "WAKE": "#eb5757",
}

DOMAIN_COLORS = {
    "PD_AON": "#6c757d",
    "PD_CPU": "#2f80ed",
    "PD_MEM": "#27ae60",
}


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def fmt(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "0.000"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def report_dir_for(report_root: Path, workload: str, tech: str, scheme: str) -> Path:
    return report_root / f"{workload}_{tech}_{scheme}"


def intent_path_for(intent_root: Path, workload: str) -> Path:
    name = workload.split("/", 1)[1] if workload.startswith("generated/") else workload
    return intent_root / name / "workload_intent.json"


def scheme_path_for(scheme_root: Path, scheme: str) -> Path:
    return scheme_root / f"{scheme}.json"


def load_case(report_root: Path, intent_root: Path, workload: str, tech: str, scheme: str) -> dict[str, Any]:
    result_dir = report_dir_for(report_root, workload, tech, scheme)
    estimate_path = result_dir / "2416_power_estimate.json"
    profile_path = result_dir / "workload_profile" / "workload_profile.json"
    if not estimate_path.exists():
        raise FileNotFoundError(f"Missing power estimate for {workload}: {estimate_path}")
    if not profile_path.exists():
        raise FileNotFoundError(f"Missing workload profile for {workload}: {profile_path}")

    estimate = load_json(estimate_path)
    profile = load_json(profile_path)
    intent_file = intent_path_for(intent_root, workload)
    intent = load_json(intent_file) if intent_file.exists() else {}
    return {
        "workload": workload,
        "label": workload.split("/")[-1],
        "report_dir": str(result_dir),
        "estimate": estimate,
        "profile": profile,
        "intent": intent,
    }


def load_scheme(scheme_root: Path, scheme: str) -> dict[str, Any]:
    path = scheme_path_for(scheme_root, scheme)
    if not path.exists():
        return {}
    return load_json(path)


def metric(case: dict[str, Any], key: str, default: float = 0.0) -> float:
    value = case["profile"].get(key, case["estimate"].get(key, default))
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def instruction_mix(case: dict[str, Any]) -> list[tuple[str, int]]:
    counts = case["profile"].get("instruction_counts", {})
    return sorted((str(name), int(count)) for name, count in counts.items())


def domain_rows(case: dict[str, Any]) -> list[dict[str, Any]]:
    return list(case["estimate"].get("domains", []))


def dominant_events(case: dict[str, Any], limit: int = 8) -> list[tuple[str, int]]:
    counts = case["estimate"].get("activity", {}).get("event_counts", {})
    rows = sorted(((str(name), int(count)) for name, count in counts.items()), key=lambda row: row[1], reverse=True)
    return rows[:limit]


def build_summary_cards(cases: list[dict[str, Any]]) -> str:
    cards: list[str] = []
    for case in cases:
        intent = case.get("intent", {})
        profile_name = intent.get("resolved_intent", {}).get("profile", "hand-written")
        macs = metric(case, "dataflow_mac_count")
        energy = metric(case, "total_energy_pj")
        useful = metric(case, "energy_per_useful_instruction_pj")
        recovery = metric(case, "recovery_energy_percent")
        memory = metric(case, "memory_intensity")
        wfi = metric(case, "wfi_density")
        rows = "".join(
            f"<li><span>{esc(name)}</span><strong>{count}</strong></li>"
            for name, count in instruction_mix(case)
        )
        cards.append(
            f"""
            <article class="workload-card">
              <div class="card-title">
                <h3>{esc(case["label"])}</h3>
                <span>{esc(profile_name)}</span>
              </div>
              <div class="metric-grid">
                <div><b>{fmt(energy, 2)}</b><span>pJ total</span></div>
                <div><b>{fmt(useful, 2)}</b><span>pJ/useful instr</span></div>
                <div><b>{fmt(macs, 0)}</b><span>dataflow MACs</span></div>
                <div><b>{fmt(recovery, 1)}%</b><span>recovery energy</span></div>
                <div><b>{fmt(memory, 3)}</b><span>memory intensity</span></div>
                <div><b>{fmt(wfi, 3)}</b><span>WFI density</span></div>
              </div>
              <ul class="instruction-list">{rows}</ul>
            </article>
            """
        )
    return "\n".join(cards)


def build_tradeoff_chart(cases: list[dict[str, Any]], key: str, title: str, unit: str, color: str) -> str:
    width = 860
    height = 300
    left = 76
    right = 24
    top = 44
    bottom = 78
    plot_w = width - left - right
    plot_h = height - top - bottom
    values = [metric(case, key) for case in cases]
    max_value = max(values) * 1.15 if values and max(values) else 1.0
    gap = 22
    bar_w = max(34, (plot_w - gap * (len(cases) + 1)) / max(len(cases), 1))

    def y(value: float) -> float:
        return top + plot_h - (value / max_value) * plot_h

    parts = [
        f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">',
        f'<text x="24" y="28" class="chart-title">{esc(title)}</text>',
    ]
    for idx in range(5):
        value = max_value * idx / 4
        yy = y(value)
        parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width - right}" y2="{yy:.2f}" class="grid-line"/>')
        parts.append(f'<text x="{left - 8}" y="{yy + 4:.2f}" text-anchor="end" class="axis-label">{fmt(value, 1)}</text>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" class="axis-line"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis-line"/>')

    for idx, case in enumerate(cases):
        value = values[idx]
        x = left + gap + idx * (bar_w + gap)
        yy = y(value)
        parts.append(
            f'<rect x="{x:.2f}" y="{yy:.2f}" width="{bar_w:.2f}" height="{top + plot_h - yy:.2f}" '
            f'fill="{color}" opacity="0.88" rx="5"/>'
        )
        parts.append(f'<text x="{x + bar_w / 2:.2f}" y="{yy - 7:.2f}" text-anchor="middle" class="value-label">{fmt(value, 2)} {esc(unit)}</text>')
        parts.append(
            f'<text x="{x + bar_w / 2:.2f}" y="{top + plot_h + 21}" text-anchor="middle" '
            f'class="axis-label rotate-label" transform="rotate(25 {x + bar_w / 2:.2f} {top + plot_h + 21})">{esc(case["label"])}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def build_domain_chart(case: dict[str, Any]) -> str:
    rows = domain_rows(case)
    total = sum(float(row.get("total_pj", 0.0)) for row in rows) or 1.0
    segments: list[str] = []
    x = 0.0
    for row in rows:
        domain = str(row.get("domain", ""))
        energy = float(row.get("total_pj", 0.0))
        width = energy / total * 100.0
        color = DOMAIN_COLORS.get(domain, "#888")
        segments.append(f'<span style="width:{width:.2f}%;background:{color}" title="{esc(domain)} {fmt(energy, 2)} pJ"></span>')
        x += width
    labels = "".join(
        f'<li><i style="background:{DOMAIN_COLORS.get(str(row.get("domain", "")), "#888")}"></i>{esc(row.get("domain", ""))}: {fmt(row.get("total_pj", 0.0), 2)} pJ</li>'
        for row in rows
    )
    return f'<div class="domain-stack">{ "".join(segments) }</div><ul class="legend compact">{labels}</ul>'


def build_datapath_animation() -> str:
    return """
    <svg class="datapath" viewBox="0 0 980 360" role="img" aria-label="Animated CPU datapath">
      <defs>
        <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto">
          <path d="M0,0 L10,4 L0,8 Z" fill="#506070"/>
        </marker>
      </defs>
      <rect x="28" y="42" width="130" height="72" rx="8" class="block aon"/>
      <text x="93" y="83" text-anchor="middle">power_controller</text>
      <rect x="210" y="42" width="120" height="72" rx="8" class="block cpu"/>
      <text x="270" y="83" text-anchor="middle">fetch</text>
      <rect x="372" y="42" width="120" height="72" rx="8" class="block cpu"/>
      <text x="432" y="83" text-anchor="middle">instr_rom</text>
      <rect x="210" y="152" width="120" height="72" rx="8" class="block cpu"/>
      <text x="270" y="193" text-anchor="middle">decode</text>
      <rect x="372" y="152" width="120" height="72" rx="8" class="block cpu"/>
      <text x="432" y="193" text-anchor="middle">regfile</text>
      <rect x="534" y="152" width="108" height="72" rx="8" class="block cpu"/>
      <text x="588" y="193" text-anchor="middle">execute</text>
      <rect x="674" y="152" width="96" height="72" rx="8" class="block cpu"/>
      <text x="722" y="193" text-anchor="middle">LSU</text>
      <rect x="802" y="152" width="104" height="72" rx="8" class="block mem"/>
      <text x="854" y="193" text-anchor="middle">data bus</text>
      <rect x="802" y="48" width="130" height="72" rx="8" class="block mem"/>
      <text x="867" y="89" text-anchor="middle">data_sram</text>
      <rect x="802" y="256" width="130" height="72" rx="8" class="block cpu"/>
      <text x="867" y="297" text-anchor="middle">dataflow_unit</text>
      <path d="M330,78 H372" class="edge"/>
      <path d="M432,114 V132 C432,145 330,137 302,152" class="edge"/>
      <path d="M330,188 H372" class="edge"/>
      <path d="M492,188 H534" class="edge"/>
      <path d="M642,188 H674" class="edge"/>
      <path d="M770,188 H802" class="edge"/>
      <path d="M854,152 C854,124 858,102 867,120" class="edge"/>
      <path d="M854,224 C854,246 858,270 867,256" class="edge"/>
      <path d="M158,78 H210" class="edge dashed"/>
      <circle r="8" class="packet packet-fetch"><animateMotion dur="4.8s" repeatCount="indefinite" path="M270,78 H432 V114 V132 C432,145 330,137 302,152 H270"/></circle>
      <circle r="8" class="packet packet-exec"><animateMotion dur="4.8s" repeatCount="indefinite" begin="1.0s" path="M270,188 H432 H588"/></circle>
      <circle r="8" class="packet packet-mem"><animateMotion dur="4.8s" repeatCount="indefinite" begin="2.1s" path="M588,188 H722 H854 C854,124 858,102 867,84"/></circle>
      <circle r="8" class="packet packet-df"><animateMotion dur="4.8s" repeatCount="indefinite" begin="2.8s" path="M588,188 H722 H854 C854,246 858,270 867,292"/></circle>
      <text x="28" y="344" class="caption">Packets show instruction fetch/decode/execute, LSU request/response traffic, SRAM access, and MMIO offload into the dataflow MAC unit.</text>
    </svg>
    """


def build_power_timeline(case: dict[str, Any]) -> str:
    timeline = case["estimate"].get("power_timeline", [])
    if not timeline:
        return '<p class="muted">No power timeline found.</p>'
    duration = max(float(row.get("end_ns", 0.0)) for row in timeline) or 1.0
    max_power = max(float(row.get("total_mw", 0.0)) for row in timeline) or 1.0
    width = 980
    height = 260
    left = 64
    right = 24
    top = 34
    plot_h = 140
    plot_w = width - left - right
    band_y = top + plot_h + 28

    def x(value: float) -> float:
        return left + (value / duration) * plot_w

    def y(value: float) -> float:
        return top + plot_h - (value / (max_power * 1.15)) * plot_h

    parts = [
        f'<svg class="timeline" viewBox="0 0 {width} {height}" role="img" aria-label="Animated power timeline for {esc(case["label"])}">',
        f'<text x="22" y="23" class="chart-title">Power timeline: {esc(case["label"])}</text>',
    ]
    for row in timeline:
        x0 = x(float(row.get("start_ns", 0.0)))
        x1 = x(float(row.get("end_ns", 0.0)))
        base = 0.0
        for domain, color in DOMAIN_COLORS.items():
            value = float(row.get(f"{domain}_mw", 0.0))
            yy0 = y(base)
            yy1 = y(base + value)
            parts.append(
                f'<rect x="{x0:.2f}" y="{yy1:.2f}" width="{max(x1 - x0, 0.7):.2f}" '
                f'height="{max(yy0 - yy1, 0.0):.2f}" fill="{color}" opacity="0.8"/>'
            )
            base += value
    for row in timeline:
        x0 = x(float(row.get("start_ns", 0.0)))
        x1 = x(float(row.get("end_ns", 0.0)))
        state = str(row.get("state", ""))
        color = STATE_COLORS.get(state, "#ddd")
        parts.append(f'<rect x="{x0:.2f}" y="{band_y}" width="{max(x1 - x0, 0.7):.2f}" height="24" fill="{color}" opacity="0.9"/>')
    parts.append(f'<line x1="{left}" y1="{top + plot_h}" x2="{width - right}" y2="{top + plot_h}" class="axis-line"/>')
    parts.append(f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + plot_h}" class="axis-line"/>')
    parts.append(f'<line class="timeline-cursor" x1="{left}" y1="{top - 10}" x2="{left}" y2="{band_y + 32}"/>')
    parts.append(f'<text x="{left}" y="{band_y + 50}" class="axis-label">0 ns</text>')
    parts.append(f'<text x="{width - right}" y="{band_y + 50}" text-anchor="end" class="axis-label">{fmt(duration, 1)} ns</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def build_event_table(case: dict[str, Any]) -> str:
    rows = dominant_events(case)
    body = "".join(f"<tr><td>{esc(name)}</td><td>{count}</td></tr>" for name, count in rows)
    return f"""
    <table>
      <thead><tr><th>Dominant event</th><th>Count</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
    """


def build_scheme_summary(scheme: dict[str, Any], scheme_name: str) -> str:
    if not scheme:
        return f"<p>Scheme metadata for <code>{esc(scheme_name)}</code> was not found, but the report data still carries the applied scheme name.</p>"
    states = scheme.get("power_states", scheme.get("states", []))
    domains = scheme.get("domains", [])
    return f"""
    <div class="scheme-summary">
      <p><strong>{esc(scheme.get("name", scheme_name))}</strong>: {esc(scheme.get("description", "Power scheme metadata"))}</p>
      <p>{len(domains)} domains, {len(states)} power states, with the simulation harness checking power-domain legality, isolation, retention, DVFS requests, and level-shifter coverage.</p>
    </div>
    """


def html_document(cases: list[dict[str, Any]], scheme: dict[str, Any], tech: str, scheme_name: str) -> str:
    if not cases:
        raise ValueError("At least one workload case is required")
    primary = cases[0]
    energy_chart = build_tradeoff_chart(cases, "total_energy_pj", "Total Energy By Workload", "pJ", "#2f80ed")
    useful_chart = build_tradeoff_chart(cases, "energy_per_useful_instruction_pj", "Energy Per Useful Instruction", "pJ", "#27ae60")
    recovery_chart = build_tradeoff_chart(cases, "recovery_energy_percent", "Recovery Energy Share", "%", "#eb5757")
    cards = build_summary_cards(cases)
    domain_sections = "\n".join(
        f"<article class=\"domain-card\"><h3>{esc(case['label'])}</h3>{build_domain_chart(case)}</article>"
        for case in cases
    )
    event_sections = "\n".join(
        f"<article class=\"event-card\"><h3>{esc(case['label'])}</h3>{build_event_table(case)}</article>"
        for case in cases
    )
    states = "".join(
        f'<li><i style="background:{color}"></i>{esc(state)}</li>'
        for state, color in STATE_COLORS.items()
    )
    domains = "".join(
        f'<li><i style="background:{color}"></i>{esc(domain)}</li>'
        for domain, color in DOMAIN_COLORS.items()
    )
    case_json = json.dumps(
        [
            {
                "workload": case["workload"],
                "energy_pj": metric(case, "total_energy_pj"),
                "average_power_mw": metric(case, "average_power_mw"),
                "dataflow_macs": metric(case, "dataflow_mac_count"),
                "memory_intensity": metric(case, "memory_intensity"),
            }
            for case in cases
        ],
        indent=2,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Mobile CPU Visual Power Story</title>
  <style>
    :root {{
      --ink: #17202a;
      --muted: #5d6d7e;
      --line: #d8dee9;
      --panel: #ffffff;
      --soft: #f5f7fb;
      --aon: {DOMAIN_COLORS["PD_AON"]};
      --cpu: {DOMAIN_COLORS["PD_CPU"]};
      --mem: {DOMAIN_COLORS["PD_MEM"]};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      color: var(--ink);
      background: #eef2f7;
      line-height: 1.5;
    }}
    header {{
      padding: 34px max(28px, calc((100vw - 1180px) / 2)) 26px;
      background: #102033;
      color: white;
    }}
    header p {{ max-width: 820px; color: #dce6f2; margin: 8px 0 0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    section {{ margin: 0 0 28px; }}
    h1, h2, h3 {{ margin: 0; letter-spacing: 0; }}
    h1 {{ font-size: 34px; }}
    h2 {{ font-size: 23px; margin-bottom: 12px; }}
    h3 {{ font-size: 16px; }}
    code {{ background: #e9edf5; padding: 2px 5px; border-radius: 4px; }}
    .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 20px;
      box-shadow: 0 10px 26px rgba(16, 32, 51, 0.06);
    }}
    .two-col {{ display: grid; grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.6fr); gap: 18px; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 16px; }}
    .workload-card, .domain-card, .event-card {{
      background: #fff;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 16px;
    }}
    .card-title {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
    .card-title span {{ color: var(--muted); font-size: 12px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; margin: 14px 0; }}
    .metric-grid div {{ background: var(--soft); border-radius: 6px; padding: 10px; min-height: 68px; }}
    .metric-grid b {{ display: block; font-size: 18px; }}
    .metric-grid span {{ color: var(--muted); font-size: 12px; }}
    .instruction-list, .legend {{ list-style: none; padding: 0; margin: 0; }}
    .instruction-list li {{ display: flex; justify-content: space-between; border-top: 1px solid #edf0f5; padding: 5px 0; font-size: 13px; }}
    .datapath, .timeline, .chart {{ width: 100%; height: auto; display: block; }}
    .block {{ fill: #fff; stroke-width: 2; }}
    .block.aon {{ stroke: var(--aon); fill: #f6f7f8; }}
    .block.cpu {{ stroke: var(--cpu); fill: #edf5ff; }}
    .block.mem {{ stroke: var(--mem); fill: #eefaf2; }}
    .edge {{ fill: none; stroke: #506070; stroke-width: 2.2; marker-end: url(#arrow); }}
    .edge.dashed {{ stroke-dasharray: 7 5; }}
    .packet {{ fill: #f2994a; filter: drop-shadow(0 1px 2px rgba(0,0,0,0.25)); }}
    .packet-exec {{ fill: #2f80ed; }}
    .packet-mem {{ fill: #27ae60; }}
    .packet-df {{ fill: #9b51e0; }}
    .caption, .axis-label {{ fill: #5d6d7e; font-size: 12px; }}
    .chart-title {{ fill: #17202a; font-size: 18px; font-weight: 700; }}
    .grid-line {{ stroke: #e3e8f1; }}
    .axis-line {{ stroke: #1f2937; stroke-width: 1; }}
    .value-label {{ fill: #334155; font-size: 11px; }}
    .timeline-cursor {{
      stroke: #111827;
      stroke-width: 2.6;
      animation: sweep 7s linear infinite;
    }}
    @keyframes sweep {{
      from {{ transform: translateX(0); }}
      to {{ transform: translateX(892px); }}
    }}
    .domain-stack {{ display: flex; height: 24px; overflow: hidden; border-radius: 5px; margin: 12px 0; background: #e9edf5; }}
    .domain-stack span {{ display: block; min-width: 1px; }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 12px; color: var(--muted); font-size: 13px; }}
    .legend.compact {{ display: block; }}
    .legend.compact li {{ margin-bottom: 4px; }}
    .legend i {{ display: inline-block; width: 12px; height: 12px; margin-right: 6px; vertical-align: -1px; border-radius: 2px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
    th, td {{ border-bottom: 1px solid #edf0f5; padding: 7px 6px; text-align: left; }}
    th {{ color: var(--muted); font-weight: 600; }}
    .muted {{ color: var(--muted); }}
    .code-data {{ white-space: pre-wrap; overflow: auto; max-height: 220px; background: #111827; color: #d1e7ff; border-radius: 8px; padding: 14px; font-size: 12px; }}
    @media (max-width: 820px) {{
      main {{ padding: 16px; }}
      .two-col {{ grid-template-columns: 1fr; }}
      h1 {{ font-size: 28px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Mobile CPU Visual Power Story</h1>
    <p>Technology <code>{esc(tech)}</code>, scheme <code>{esc(scheme_name)}</code>. This dashboard connects workload intent, CPU activity, power states, and IEEE 2416 estimates.</p>
  </header>
  <main>
    <section class="two-col">
      <div class="panel">
        <h2>How The CPU Moves Work</h2>
        {build_datapath_animation()}
      </div>
      <aside class="panel">
        <h2>Power Strategy</h2>
        {build_scheme_summary(scheme, scheme_name)}
        <h3>States</h3>
        <ul class="legend">{states}</ul>
        <h3 style="margin-top:16px">Domains</h3>
        <ul class="legend">{domains}</ul>
      </aside>
    </section>

    <section class="panel">
      <h2>Animated Power Timeline</h2>
      <p class="muted">The stacked area shows estimated power by domain. The mode band underneath shows how the same workload moves through RUN, idle, sleep, deep sleep, and wake recovery.</p>
      {build_power_timeline(primary)}
    </section>

    <section>
      <h2>Workload Cards</h2>
      <div class="cards">{cards}</div>
    </section>

    <section class="panel">
      <h2>Power Tradeoffs</h2>
      <p class="muted">Use these charts to compare whether energy is dominated by useful computation, offload traffic, low-power recovery, or memory behavior.</p>
      {energy_chart}
      {useful_chart}
      {recovery_chart}
    </section>

    <section>
      <h2>Energy By Domain</h2>
      <div class="cards">{domain_sections}</div>
    </section>

    <section>
      <h2>Dominant Activity Events</h2>
      <div class="cards">{event_sections}</div>
    </section>

    <section class="panel">
      <h2>Flow Map</h2>
      <p><code>workload_specs/*.json</code> or <code>workloads/*.s</code> produces ROM contents, Verilator produces VCD activity, the IEEE 2416 estimator maps activity to block/domain energy, and this dashboard explains the resulting tradeoffs.</p>
      <pre class="code-data">{esc(case_json)}</pre>
    </section>
  </main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload", action="append", dest="workloads", required=True)
    parser.add_argument("--tech", default="generic_7nm")
    parser.add_argument("--scheme", default="dvfs_retention_domains")
    parser.add_argument("--report-root", type=Path, default=Path("reports/2416"))
    parser.add_argument("--intent-root", type=Path, default=Path("build/workloadgen"))
    parser.add_argument("--scheme-root", type=Path, default=Path("power_schemes"))
    parser.add_argument("--out", type=Path, default=Path("reports/visual_story/index.html"))
    args = parser.parse_args()

    cases = [
        load_case(args.report_root, args.intent_root, workload, args.tech, args.scheme)
        for workload in args.workloads
    ]
    scheme = load_scheme(args.scheme_root, args.scheme)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html_document(cases, scheme, args.tech, args.scheme), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
