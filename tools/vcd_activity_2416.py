#!/usr/bin/env python3
"""Extract IEEE 2416 activity observations from a Verilator VCD."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


DUT = "TOP.mobile_cpu_power_top.u_dut"

BLOCK_PATHS = {
    "fetch_unit": f"{DUT}.u_fetch",
    "instr_rom": f"{DUT}.u_icache",
    "decode_unit": f"{DUT}.u_decode",
    "regfile": f"{DUT}.u_regfile",
    "execute_unit": f"{DUT}.u_execute",
    "data_sram": f"{DUT}.u_dmem",
    "dataflow_unit": f"{DUT}.u_dataflow",
    "power_controller": f"{DUT}.u_power_controller",
}

MODE_NAMES = {
    0: "RUN",
    1: "IDLE",
    2: "LIGHT_SLEEP",
    3: "DEEP_SLEEP",
    4: "WAKE",
}

OPCODE_EVENTS = {
    0x1: ("execute_unit", "alu_add"),
    0x2: ("execute_unit", "alu_sub"),
    0x3: ("execute_unit", "alu_and"),
    0x4: ("execute_unit", "alu_or"),
    0x5: ("execute_unit", "alu_addi"),
    0x8: ("execute_unit", "branch_compare"),
    0xF: ("execute_unit", "wait_for_interrupt"),
}

OPCODE_NAMES = {
    0x0: "NOP",
    0x1: "ADD",
    0x2: "SUB",
    0x3: "AND",
    0x4: "OR",
    0x5: "ADDI",
    0x6: "LD",
    0x7: "ST",
    0x8: "BEQ",
    0xF: "WFI",
}

DATAFLOW_MMIO_BASE = 4
DATAFLOW_MMIO_LIMIT = 7


def parse_timescale_ps(line: str) -> float:
    parts = line.split()
    if len(parts) < 2:
        return 1.0
    try:
        value = float(parts[1])
        unit = parts[2] if len(parts) > 2 else "ps"
    except ValueError:
        return 1.0
    unit_to_ps = {
        "s": 1e12,
        "ms": 1e9,
        "us": 1e6,
        "ns": 1e3,
        "ps": 1.0,
        "fs": 1e-3,
    }
    return value * unit_to_ps.get(unit, 1.0)


def int_value(value: str | None) -> int:
    if value is None:
        return 0
    value = value.lower().replace("x", "0").replace("z", "0")
    if not value:
        return 0
    if all(ch in "01" for ch in value):
        return int(value, 2)
    return int(value[0], 2) if value[0] in "01" else 0


def bit_value(value: str | None) -> int:
    return int_value(value) & 1


def hamming(old: str | None, new: str | None) -> int:
    if old is None or new is None or old == new:
        return 0
    width = max(len(old), len(new))
    old_bits = old.lower().replace("x", "0").replace("z", "0").zfill(width)
    new_bits = new.lower().replace("x", "0").replace("z", "0").zfill(width)
    return sum(1 for a, b in zip(old_bits, new_bits) if a != b)


class VcdActivityExtractor:
    def __init__(self, vcd_path: Path):
        self.vcd_path = vcd_path
        self.timescale_ps = 1.0
        self.code_to_paths: dict[str, list[str]] = defaultdict(list)
        self.code_to_size: dict[str, int] = {}
        self.path_to_code: dict[str, str] = {}
        self.values: dict[str, str] = {}
        self.current_time = 0
        self.duration_ps = 0

        self.state_durations_ps: dict[str, float] = defaultdict(float)
        self.dvfs_durations_ps: dict[str, float] = defaultdict(float)
        self.clock_cycles: dict[str, int] = defaultdict(int)
        self.clock_cycles_by_dvfs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.event_counts: dict[str, int] = defaultdict(int)
        self.event_counts_by_dvfs: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.instruction_counts: dict[str, int] = defaultdict(int)
        self.block_toggles: dict[str, int] = defaultdict(int)
        self.mode_transitions: dict[str, int] = defaultdict(int)
        self.state_timeline: list[dict] = []

    def extract(self) -> dict:
        header_done = False
        scope: list[str] = []
        batch: list[str] = []

        for raw_line in self.vcd_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if not header_done:
                if line.startswith("$timescale"):
                    self.timescale_ps = parse_timescale_ps(line)
                elif line.startswith("$scope"):
                    parts = line.split()
                    if len(parts) >= 3:
                        scope.append(parts[2])
                elif line.startswith("$upscope"):
                    if scope:
                        scope.pop()
                elif line.startswith("$var"):
                    self._parse_var(line, scope)
                elif line.startswith("$enddefinitions"):
                    header_done = True
                continue

            if line.startswith("#"):
                self._process_batch(batch)
                batch = []
                new_time = int(line[1:])
                self._accumulate_duration(new_time - self.current_time)
                self.current_time = new_time
            else:
                batch.append(line)

        self._process_batch(batch)
        self.duration_ps = self.current_time * self.timescale_ps
        return self._to_dict()

    def _parse_var(self, line: str, scope: list[str]) -> None:
        parts = line.split()
        if len(parts) < 5:
            return
        size = int(parts[2])
        code = parts[3]
        name = parts[4]
        full_path = ".".join(scope + [name])
        self.code_to_paths[code].append(full_path)
        self.code_to_size[code] = max(self.code_to_size.get(code, 0), size)
        self.path_to_code[full_path] = code

    def _code(self, path: str) -> str | None:
        return self.path_to_code.get(path)

    def _value(self, path: str) -> str | None:
        code = self._code(path)
        return self.values.get(code) if code else None

    def _mode(self) -> str:
        mode = int_value(self._value(f"{DUT}.power_mode"))
        return MODE_NAMES.get(mode, f"UNKNOWN_{mode}")

    def _dvfs(self) -> str:
        return str(int_value(self._value(f"{DUT}.dvfs_level")))

    def _reset_released(self) -> bool:
        return bit_value(self._value(f"{DUT}.reset_n")) == 1

    def _accumulate_duration(self, raw_delta: int) -> None:
        if raw_delta <= 0:
            return
        delta_ps = raw_delta * self.timescale_ps
        mode = self._mode()
        dvfs = self._dvfs()
        start_ps = self.current_time * self.timescale_ps
        end_ps = (self.current_time + raw_delta) * self.timescale_ps
        self.state_durations_ps[mode] += delta_ps
        self.dvfs_durations_ps[dvfs] += delta_ps
        if self.state_timeline and self.state_timeline[-1]["state"] == mode and self.state_timeline[-1]["dvfs"] == dvfs:
            self.state_timeline[-1]["end_ps"] = end_ps
            self.state_timeline[-1]["duration_ps"] += delta_ps
        else:
            self.state_timeline.append(
                {
                    "start_ps": start_ps,
                    "end_ps": end_ps,
                    "duration_ps": delta_ps,
                    "state": mode,
                    "dvfs": dvfs,
                }
            )

    def _parse_change(self, line: str) -> tuple[str, str] | None:
        if line[0] in "01xXzZ":
            return line[1:], line[0].lower()
        if line[0] in "bBrR":
            parts = line.split()
            if len(parts) == 2:
                return parts[1], parts[0][1:].lower()
        return None

    def _process_batch(self, batch: list[str]) -> None:
        if not batch:
            return

        watched_codes = {
            "top_clk": self._code(f"{DUT}.clk"),
            "core_clk": self._code(f"{DUT}.core_clk"),
            "mem_clk": self._code(f"{DUT}.mem_clk"),
            "power_mode": self._code(f"{DUT}.power_mode"),
        }
        old_values = {name: self.values.get(code) for name, code in watched_codes.items() if code}

        for line in batch:
            change = self._parse_change(line)
            if not change:
                continue
            code, new_value = change
            old_value = self.values.get(code)
            self.values[code] = new_value
            self._count_toggles(code, old_value, new_value)

        self._count_mode_transition(old_values.get("power_mode"))
        if self._posedge(old_values.get("top_clk"), self._value(f"{DUT}.clk")):
            self._sample_top_edge()
        if self._posedge(old_values.get("core_clk"), self._value(f"{DUT}.core_clk")):
            self._sample_core_edge()
        if self._posedge(old_values.get("mem_clk"), self._value(f"{DUT}.mem_clk")):
            self._sample_mem_edge()

    def _posedge(self, old_value: str | None, new_value: str | None) -> bool:
        return bit_value(old_value) == 0 and bit_value(new_value) == 1

    def _count_toggles(self, code: str, old_value: str | None, new_value: str | None) -> None:
        count = hamming(old_value, new_value)
        if count == 0:
            return
        paths = self.code_to_paths.get(code, [])
        for block, prefix in BLOCK_PATHS.items():
            if any(path.startswith(prefix) for path in paths):
                self.block_toggles[block] += count

    def _count_mode_transition(self, old_mode_value: str | None) -> None:
        if not self._reset_released():
            return
        old_mode = MODE_NAMES.get(int_value(old_mode_value), None)
        new_mode = self._mode()
        if old_mode and old_mode != new_mode:
            transition = f"{old_mode}->{new_mode}"
            self.mode_transitions[transition] += 1
            self._add_event("power_controller", "mode_transition")

    def _add_event(self, block: str, event: str, count: int = 1) -> None:
        key = f"{block}.{event}"
        self.event_counts[key] += count
        self.event_counts_by_dvfs[key][self._dvfs()] += count

    def _sample_top_edge(self) -> None:
        if not self._reset_released():
            return
        self.clock_cycles["top"] += 1
        self.clock_cycles_by_dvfs["top"][self._dvfs()] += 1

    def _sample_mem_edge(self) -> None:
        if not self._reset_released():
            return
        if bit_value(self._value(f"{DUT}.mem_power_gate_n")) == 0:
            return
        self.clock_cycles["mem"] += 1
        self.clock_cycles_by_dvfs["mem"][self._dvfs()] += 1
        if bit_value(self._value(f"{DUT}.dataflow_op_valid")):
            self._add_event("dataflow_unit", "mac_accumulate")

    def _sample_core_edge(self) -> None:
        if not self._reset_released():
            return
        if bit_value(self._value(f"{DUT}.cpu_power_gate_n")) == 0:
            return

        self.clock_cycles["core"] += 1
        self.clock_cycles_by_dvfs["core"][self._dvfs()] += 1

        instr = int_value(self._value(f"{DUT}.instr"))
        opcode = (instr >> 12) & 0xF
        retired = bit_value(self._value(f"{DUT}.retired"))
        if not retired:
            return
        self.instruction_counts[OPCODE_NAMES.get(opcode, f"OP_{opcode:x}")] += 1

        self._add_event("fetch_unit", "pc_update")
        self._add_event("instr_rom", "instruction_fetch")
        self._add_event("decode_unit", "decode_instruction")

        if opcode in OPCODE_EVENTS:
            block, event = OPCODE_EVENTS[opcode]
            self._add_event(block, event)

        if opcode in {0x1, 0x2, 0x3, 0x4, 0x8}:
            self._add_event("regfile", "read", 2)
        elif opcode in {0x5, 0x6}:
            self._add_event("regfile", "read", 1)
        elif opcode == 0x7:
            self._add_event("regfile", "read", 2)

        if opcode in {0x1, 0x2, 0x3, 0x4, 0x5, 0x6}:
            self._add_event("regfile", "write")

        if opcode in {0x6, 0x7}:
            self._sample_memory_mapped_event(opcode)

        if opcode == 0x8 and bit_value(self._value(f"{DUT}.branch_taken")):
            self._add_event("fetch_unit", "branch_redirect")

    def _sample_memory_mapped_event(self, opcode: int) -> None:
        mem_addr = int_value(self._value(f"{DUT}.mem_addr"))
        mem_wdata = int_value(self._value(f"{DUT}.mem_wdata"))
        if DATAFLOW_MMIO_BASE <= mem_addr <= DATAFLOW_MMIO_LIMIT:
            offset = mem_addr - DATAFLOW_MMIO_BASE
            if opcode == 0x6:
                if offset == 2:
                    self._add_event("dataflow_unit", "status_read")
                elif offset == 3:
                    self._add_event("dataflow_unit", "result_read")
                else:
                    self._add_event("dataflow_unit", "operand_read")
            else:
                if offset in {0, 1}:
                    self._add_event("dataflow_unit", "operand_write")
                elif offset == 2:
                    self._add_event("dataflow_unit", "command_write")
                    if mem_wdata & 0x2:
                        self._add_event("dataflow_unit", "accumulator_clear")
                else:
                    self._add_event("dataflow_unit", "repeat_count_write")
            return

        if opcode == 0x6:
            self._add_event("data_sram", "read")
        elif opcode == 0x7:
            self._add_event("data_sram", "write")

    def _to_dict(self) -> dict:
        return {
            "source": str(self.vcd_path),
            "timescale_ps": self.timescale_ps,
            "duration_ps": self.duration_ps,
            "state_durations_ps": dict(sorted(self.state_durations_ps.items())),
            "dvfs_durations_ps": dict(sorted(self.dvfs_durations_ps.items())),
            "clock_cycles": dict(sorted(self.clock_cycles.items())),
            "clock_cycles_by_dvfs": {
                clock: dict(sorted(counts.items()))
                for clock, counts in sorted(self.clock_cycles_by_dvfs.items())
            },
            "event_counts": dict(sorted(self.event_counts.items())),
            "event_counts_by_dvfs": {
                event: dict(sorted(counts.items()))
                for event, counts in sorted(self.event_counts_by_dvfs.items())
            },
            "instruction_counts": dict(sorted(self.instruction_counts.items())),
            "retired_instruction_count": sum(self.instruction_counts.values()),
            "block_toggles": dict(sorted(self.block_toggles.items())),
            "mode_transitions": dict(sorted(self.mode_transitions.items())),
            "state_timeline": self.state_timeline,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vcd", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("reports/2416/activity.json"))
    args = parser.parse_args()

    activity = VcdActivityExtractor(args.vcd).extract()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(activity, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
