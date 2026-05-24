#!/usr/bin/env python3
"""Assemble the toy mobile CPU instruction format into a memh ROM image."""

from __future__ import annotations

import argparse
import re
from pathlib import Path


OPCODES = {
    "NOP": 0x0,
    "ADD": 0x1,
    "SUB": 0x2,
    "AND": 0x3,
    "OR": 0x4,
    "ADDI": 0x5,
    "LD": 0x6,
    "ST": 0x7,
    "BEQ": 0x8,
    "WFI": 0xF,
}


def strip_comment(line: str) -> str:
    for marker in ("#", "//", ";"):
        if marker in line:
            line = line[: line.index(marker)]
    return line.strip()


def split_operands(text: str) -> list[str]:
    operands: list[str] = []
    current: list[str] = []
    bracket_depth = 0
    for char in text:
        if char == "[":
            bracket_depth += 1
        elif char == "]":
            bracket_depth -= 1
        if char == "," and bracket_depth == 0:
            operands.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        operands.append("".join(current).strip())
    return operands


def parse_reg(text: str) -> int:
    match = re.fullmatch(r"[rR](\d+)", text.strip())
    if not match:
        raise ValueError(f"Expected register r0-r15, got {text!r}")
    value = int(match.group(1), 10)
    if value < 0 or value > 15:
        raise ValueError(f"Register out of range: {text!r}")
    return value


def parse_imm(text: str) -> int:
    value = int(text.strip(), 0)
    if value < -8 or value > 15:
        raise ValueError(f"Immediate must fit 4 bits signed/unsigned, got {value}")
    return value & 0xF


def parse_mem_operand(text: str) -> tuple[int, int]:
    match = re.fullmatch(r"\[\s*([rR]\d+)\s*(?:\+\s*([-+]?(?:0x[0-9a-fA-F]+|\d+)))?\s*\]", text.strip())
    if not match:
        raise ValueError(f"Expected memory operand like [r0 + 4], got {text!r}")
    base = parse_reg(match.group(1))
    imm = parse_imm(match.group(2) or "0")
    return base, imm


def encode(opcode: str, operands: list[str]) -> int:
    op = opcode.upper()
    if op not in OPCODES:
        raise ValueError(f"Unknown opcode {opcode!r}")

    code = OPCODES[op]
    if op in {"NOP", "WFI"}:
        if operands:
            raise ValueError(f"{op} takes no operands")
        return code << 12

    if op in {"ADD", "SUB", "AND", "OR"}:
        if len(operands) != 3:
            raise ValueError(f"{op} expects rd, rs1, rs2")
        rd = parse_reg(operands[0])
        rs1 = parse_reg(operands[1])
        rs2 = parse_reg(operands[2])
        return (code << 12) | (rd << 8) | (rs1 << 4) | rs2

    if op == "ADDI":
        if len(operands) != 3:
            raise ValueError("ADDI expects rd, rs1, imm")
        rd = parse_reg(operands[0])
        rs1 = parse_reg(operands[1])
        imm = parse_imm(operands[2])
        return (code << 12) | (rd << 8) | (rs1 << 4) | imm

    if op == "LD":
        if len(operands) != 2:
            raise ValueError("LD expects rd, [base + imm]")
        rd = parse_reg(operands[0])
        base, imm = parse_mem_operand(operands[1])
        return (code << 12) | (rd << 8) | (base << 4) | imm

    if op == "ST":
        if len(operands) != 2:
            raise ValueError("ST expects rs, [base + imm]")
        rs = parse_reg(operands[0])
        base, imm = parse_mem_operand(operands[1])
        return (code << 12) | (rs << 8) | (base << 4) | imm

    if op == "BEQ":
        if len(operands) != 3:
            raise ValueError("BEQ expects rs1, rs2, offset")
        rs1 = parse_reg(operands[0])
        rs2 = parse_reg(operands[1])
        offset = parse_imm(operands[2])
        if rs2 != offset:
            raise ValueError("This toy BEQ encoding shares rs2 and offset; use matching values")
        return (code << 12) | (0 << 8) | (rs1 << 4) | rs2

    raise AssertionError(f"Unhandled opcode {op}")


def assemble(path: Path) -> list[tuple[int, str, int]]:
    assembled: list[tuple[int, str, int]] = []
    for line_no, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = strip_comment(raw_line)
        if not line:
            continue
        parts = line.split(None, 1)
        opcode = parts[0]
        operands = split_operands(parts[1]) if len(parts) > 1 else []
        try:
            word = encode(opcode, operands)
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: {exc}") from exc
        assembled.append((line_no, raw_line.strip(), word))
    return assembled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--memh", type=Path, required=True)
    parser.add_argument("--listing", type=Path)
    parser.add_argument("--depth", type=int, default=64)
    args = parser.parse_args()

    assembled = assemble(args.input)
    if len(assembled) > args.depth:
        raise ValueError(f"Program has {len(assembled)} instructions but depth is {args.depth}")

    args.memh.parent.mkdir(parents=True, exist_ok=True)
    args.memh.write_text(
        "\n".join(f"{word:04x}" for _, _, word in assembled) + "\n",
        encoding="utf-8",
    )

    if args.listing:
        args.listing.parent.mkdir(parents=True, exist_ok=True)
        lines = [
            f"{idx:04x}: {word:04x}    {source}"
            for idx, (_, source, word) in enumerate(assembled)
        ]
        args.listing.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"assembled {args.input} -> {args.memh} ({len(assembled)} instructions)")


if __name__ == "__main__":
    main()

