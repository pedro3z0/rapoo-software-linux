#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pe_xrefs.py - find *code references* to strings and constants inside a PE.

Built for the Rapoo reverse-engineering effort: locate the functions in
RapooDevice.dll that build and send HID reports, by xref-ing the dynamically
resolved hidapi entry points ("hid_send_feature_report", ...) and the protocol
constants (frame magic, report ids, ...).

Examples:
    # list all strings that contain "hid_" together with their virtual addresses
    pe_xrefs.py RapooDevice.dll --strings hid_

    # find code that references a string (32-bit absolute or RIP-relative)
    pe_xrefs.py RapooDevice.dll --string hid_send_feature_report

    # find code referencing an immediate constant (frame magic 0xBAA5AE)
    pe_xrefs.py RapooDevice.dll --imm 0xBAA5AE

    # raise the number of disassembled context instructions around each hit
    pe_xrefs.py RapooDevice.dll --string hid_write --context 30
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pefile
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_MODE_64, CS_OP_IMM, CS_OP_MEM


def load_sections(pe: pefile.PE) -> list[dict]:
    sections = []
    for sec in pe.sections:
        name = sec.Name.rstrip(b"\x00").decode("latin1", "replace")
        sections.append(
            {
                "name": name,
                "va": sec.VirtualAddress,
                "vsize": sec.Misc_VirtualSize,
                "data": sec.get_data(),
                "exec": bool(sec.Characteristics & 0x20000000),
            }
        )
    return sections


def va_to_offset(sections: list[dict], va: int, image_base: int) -> int | None:
    rva = va - image_base
    for sec in sections:
        span = max(len(sec["data"]), sec["vsize"])
        if sec["va"] <= rva < sec["va"] + span:
            return rva - sec["va"]
    return None


def find_strings(sections: list[dict], needle: bytes, image_base: int, limit: int) -> list[tuple[int, str]]:
    hits = []
    for sec in sections:
        start = 0
        while len(hits) < limit:
            idx = sec["data"].find(needle, start)
            if idx < 0:
                break
            va = image_base + sec["va"] + idx
            end = sec["data"].find(b"\x00", idx)
            text = sec["data"][idx : end if end > 0 else idx + 200]
            hits.append((va, text.decode("latin1", "replace")))
            start = idx + 1
    return hits


def disassemble(sections: list[dict], image_base: int, bits: int) -> tuple[Cs, list]:
    md = Cs(CS_ARCH_X86, CS_MODE_32 if bits == 32 else CS_MODE_64)
    md.detail = True
    instructions = []
    for sec in sections:
        if not sec["exec"]:
            continue
        va = image_base + sec["va"]
        for insn in md.disasm(sec["data"], va):
            instructions.append(insn)
    return md, instructions


def insn_refs(insn, target: int) -> list[str]:
    """Return descriptions of operands in *insn* that equal *target*."""
    found = []
    try:
        operands = insn.operands
    except Exception:
        return found
    for op in operands:
        if op.type == CS_OP_IMM:
            value = op.imm & 0xFFFFFFFF
            if value == (target & 0xFFFFFFFF):
                found.append(f"imm=0x{value:08X}")
        elif op.type == CS_OP_MEM:
            disp = op.mem.disp & 0xFFFFFFFF
            if disp == (target & 0xFFFFFFFF):
                found.append(f"mem=0x{disp:08X}")
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Find code references to strings/constants in a PE.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("pe_file", type=Path)
    grp = ap.add_mutually_exclusive_group(required=True)
    grp.add_argument("--string", help="find code refs to this exact string")
    grp.add_argument("--strings", help="list strings containing this needle, with VAs")
    grp.add_argument("--imm", type=str, help="comma-separated constants to find refs to")
    grp.add_argument("--exports", action="store_true", help="list exported symbols with VAs")
    grp.add_argument("--disasm", type=lambda s: int(s, 0), help="linear disassembly at VA")
    ap.add_argument("--len", type=lambda s: int(s, 0), default=256, help="bytes for --disasm")
    ap.add_argument("--context", type=int, default=12, help="instructions around each hit")
    ap.add_argument("--limit", type=int, default=20, help="max hits to print")
    args = ap.parse_args(argv)

    pe = pefile.PE(str(args.pe_file), fast_load=True)
    bits = 64 if pe.FILE_HEADER.Machine == 0x8664 else 32
    image_base = pe.OPTIONAL_HEADER.ImageBase
    sections = load_sections(pe)
    print(f"{args.pe_file.name}: {bits}-bit, image base 0x{image_base:08X}")
    print(f"sections: {', '.join(s['name'] for s in sections)}")

    if args.strings is not None:
        hits = find_strings(sections, args.strings.encode(), image_base, args.limit)
        for va, text in hits:
            print(f"0x{va:08X}  {text[:140]}")
        print(f"total: {len(hits)}")
        return 0

    if args.exports:
        pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
        symbols = getattr(pe, "DIRECTORY_ENTRY_EXPORT", None)
        if symbols is None:
            print("no exports")
            return 1
        entries = sorted(
            (
                (image_base + sym.address, sym.name.decode("latin1") if sym.name else f"ordinal_{sym.ordinal}")
                for sym in symbols.symbols
            ),
            key=lambda item: item[0],
        )
        for va, name in entries:
            print(f"0x{va:08X}  {name}")
        print(f"total: {len(entries)}")
        return 0

    if args.disasm is not None:
        target = args.disasm
        offset = va_to_offset(sections, target, image_base)
        if offset is None:
            print(f"VA 0x{target:08X} not inside any section")
            return 1
        rva = target - image_base
        section = next(
            s for s in sections if s["va"] <= rva < s["va"] + max(len(s["data"]), s["vsize"])
        )
        data = section["data"][offset : offset + args.len]
        md = Cs(CS_ARCH_X86, CS_MODE_32 if bits == 32 else CS_MODE_64)
        print(f"disassembling {len(data)} bytes @0x{target:08X}")
        for insn in md.disasm(data, target):
            print(f"0x{insn.address:08X}: {insn.mnemonic:<8} {insn.op_str}")
        return 0

    if args.string is not None:
        hits = find_strings(sections, args.string.encode(), image_base, 1)
        if not hits:
            print(f"string not found: {args.string!r}")
            return 1
        targets = [hits[0][0]]
        print(f'string "{args.string}" @0x{targets[0]:08X}')
    else:
        targets = [int(token, 0) for token in args.imm.split(",")]
        print("immediates: " + ", ".join(f"0x{t:X}" for t in targets))

    md, instructions = disassemble(sections, image_base, bits)
    print(f"decoded {len(instructions):,} instructions")
    total = 0
    for target in targets:
        found = 0
        for i, insn in enumerate(instructions):
            refs = insn_refs(insn, target)
            if not refs:
                continue
            found += 1
            print(f"\n=== target 0x{target:X} hit {found} @0x{insn.address:08X} ({', '.join(refs)}) ===")
            for j in range(max(0, i - args.context), min(len(instructions), i + args.context + 1)):
                ins = instructions[j]
                mark = ">>" if j == i else "  "
                print(f"{mark} 0x{ins.address:08X}: {ins.mnemonic:<8} {ins.op_str}")
            if found >= args.limit:
                print(f"\n(stopped at limit {args.limit})")
                break
        total += found
    print(f"\ntotal refs: {total}")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())

