# Getting Started And Interview Guide

This project is a compact mobile CPU power-intent playground. It is designed to
show that you understand both RTL hierarchy and UPF-driven low-power
implementation planning.

## What To Show First

Start with the problem statement:

> This is a small SystemVerilog mobile CPU partitioned so different power
> optimization schemes can be explored automatically. Each JSON scheme generates
> a matching UPF file, and a simple estimator compares expected power impact.

Then show these files:

- `rtl/mobile_cpu_top.sv`: CPU hierarchy and power-control signals.
- `rtl/power_controller.sv`: idle, sleep, deep-sleep, wake, and DVFS controls.
- `power_schemes/04_dvfs_retention_domains.json`: the richest low-power scheme.
- `tools/gen_upf.py`: automatic UPF generator.
- `upf/dvfs_retention_domains.upf`: generated power intent.
- `reports/power_summary.md`: quick comparison of schemes.

## How To Clone The Repo

After this project is pushed to GitHub:

```sh
git clone https://github.com/YOUR_USER/YOUR_REPO.git
cd YOUR_REPO
```

## How To Regenerate UPF

```sh
make upf
```

This reads every JSON file in `power_schemes/` and writes generated UPF to
`upf/`.

## How To Run The Power Exploration

```sh
make explore
```

This writes:

- `reports/power_summary.csv`
- `reports/power_summary.md`

The estimates are architectural placeholders. The useful part is the comparison
between schemes, not the exact absolute milliwatts.

## How To Run Tests

```sh
make test
```

The current test verifies that every scheme can generate UPF and that important
constructs such as power switches, isolation, retention, PST states, and level
shifters appear where expected.

## How To Modify A Power Scheme

1. Copy one JSON file in `power_schemes/`.
2. Change the scheme `name`, domain list, states, switches, isolation,
   retention, or level shifters.
3. Run:

```sh
make upf explore test
```

4. Inspect the new UPF file in `upf/`.

## How To Add A New RTL Block

1. Add the SystemVerilog module under `rtl/`.
2. Instantiate it from `rtl/mobile_cpu_top.sv`.
3. Add its instance name to the right domain in the scheme JSON file.
4. Regenerate UPF:

```sh
make upf
```

## Interview Walkthrough

Use this order:

1. Explain that the RTL hierarchy was intentionally split into always-on,
   CPU-core, and memory-style blocks.
2. Show `power_controller.sv` and point out these controls:
   `core_clk_en`, `mem_clk_en`, `cpu_power_gate_n`, `mem_power_gate_n`,
   `iso_core`, `iso_mem`, `ret_save`, `ret_restore`, and `dvfs_level`.
3. Show `power_schemes/04_dvfs_retention_domains.json` and explain that it is
   the source of truth for the power strategy.
4. Run `make upf` and open `upf/dvfs_retention_domains.upf`.
5. Point out generated UPF constructs:
   `create_power_domain`, `create_power_switch`, `set_isolation`,
   `set_retention`, `set_level_shifter`, and `add_pst_state`.
6. Run `make explore` and show the summary table.
7. Run `make test` to show the automation is checked.

## Honest Limitations To Mention

- This is a design exploration model, not a tapeout-ready CPU.
- The power numbers are early architectural estimates.
- Generated UPF is intentionally tool-neutral and may need small syntax
  adjustments for a specific EDA vendor flow.
- A real flow would add synthesis, simulation, UPF-aware verification,
  equivalence checks, and physical implementation signoff.

## Strong Interview Closing

You can say:

> I built this to demonstrate the workflow: design hierarchy, define power
> domains, express strategies declaratively, generate UPF automatically, and
> compare schemes. The next step would be connecting it to a simulator or
> synthesis tool with UPF support and replacing the placeholder estimator with
> real switching activity and library data.

