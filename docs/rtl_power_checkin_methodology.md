# RTL Power/Performance Check-In Methodology

This flow turns the toy mobile CPU power exploration into a repeatable RTL
check-in methodology. It is intentionally metrics-first:

1. Generate objective workload, block, hierarchy, event, and domain metrics.
2. Compare those metrics against a saved baseline.
3. Generate designer-facing optimization cards only after the metrics exist.
4. Optionally fail CI only when configured red regressions are present.

## Commands

Generate current metrics and refresh the visual story:

```sh
make visual-story TECH=generic_7nm SCHEME=clock_gated_idle
```

Capture a baseline:

```sh
make power-baseline TECH=generic_7nm SCHEME=clock_gated_idle
```

Run a check-in comparison against that baseline:

```sh
make power-check TECH=generic_7nm SCHEME=clock_gated_idle
```

Use CI-style red-regression failure:

```sh
make power-check-ci TECH=generic_7nm SCHEME=clock_gated_idle
```

## Generated Artifacts

- `reports/power_metrics.json`: current workload, domain, block, event, and
  hierarchy metrics.
- `reports/baselines/power_metrics_baseline.json`: saved baseline from
  `make power-baseline`.
- `reports/power_metrics_delta.json`: baseline/current deltas with
  green/yellow/red/info status.
- `reports/checkin_summary.md`: compact pull-request style summary.
- `reports/power_optimization_cards.json`: advisory designer cards.
- `reports/visual_story/index.html`: visual report with check-in summary,
  metric deltas, hierarchy attribution, cards, missing data, and the existing
  animated dashboard.

## Configuration

Thresholds live in `power_check_config.json`. The defaults are advisory:

- total energy red regression above 20%
- pJ/useful-instruction red regression above 20%
- stall-cycle red regression above 30%
- MMIO transactions per MAC red above 5
- front-end active during stall red above 50%
- clock-enable efficiency red below 20%

Hierarchy attribution lives in `power_hierarchy_map.json`. Each event or block
maps to:

- RTL hierarchy
- architectural block
- related upstream/downstream hierarchy
- likely control signal or FSM
- designer hint
- likely fix pattern
- suggested additional metrics

If a future event is not mapped, the metrics file reports it in
`missing_hierarchy_mappings` so the map can be extended.

## How A Logic Designer Should Use It

During RTL review, start with `reports/checkin_summary.md`:

1. Check correctness and workload count.
2. Inspect red and yellow deltas first.
3. Use the hierarchy attribution table to find the exact RTL block/event.
4. Read only the related optimization card after the metric is understood.
5. Run the listed verification tests before accepting the RTL change.

The cards are explanatory, not the primary gate. They are meant to connect
metrics to concrete RTL actions such as descriptor-mode dataflow offload,
stall-aware front-end freezing, or split dataflow control/MAC clock enables.

## Current Known Missing Metrics

Some fields are intentionally `null` until more instrumentation is added:

- stall cycles by reason
- duplicate LSU request count
- PC update during stall cycles
- address decode during stall cycles
- explicit WFI sleep and wake recovery counters

These are listed in `reports/power_metrics.json` under `missing_metrics` with
suggested counters or signals.
