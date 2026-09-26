#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ifw_extract.py - statically extract the payload of a Qt Installer Framework
(IFW) 4.x offline installer, without ever executing it.

Verified against "A HUB_Game_Win_V1.0.19.exe" (IFW 4.6.1, Qt 5.15.2).

Layout of an IFW installer on disk (see Qt IFW binarylayout.cpp / binarycontent.cpp):

    [PE image][appended binary content][Authenticode certificate]

For the Rapoo installer the appended binary content is:

    [compiled Qt resource blob ("qres")     ~31 KB   installer meta files]
    [20 concatenated 7z archives, no gaps   320 MB   application payload]
    [IFW collection index footer                     offsets/hashes of the above]

Each archive is carved *exactly* via the standard 7z start header:

    archive_size = 32 + next_header_offset + next_header_size

Both the start-header CRC and the next-header CRC are verified before an
archive is accepted, so stray 0x377ABCAF271C bytes inside compressed data can
never fool the carving.

Outputs (defaults):

    analysis/extracted/payload/<name>.7z       carved archives
    analysis/extracted/payload/<name>/         extracted file trees
    analysis/extracted/meta/resources.rcc      compiled meta resource blob
    analysis/extracted/meta/Updates.xml        copy of the embedded Updates.xml
    analysis/manifests/payload_manifest.json   offsets, sizes, hashes, status

Usage:
    python3 tools/ifw_extract.py                 # carve + validate + extract
    python3 tools/ifw_extract.py --no-extract    # carve + validate only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import re
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INSTALLER = REPO_ROOT / "A HUB_Game_Win_V1.0.19.exe"
DEFAULT_OUT = REPO_ROOT / "analysis" / "extracted"
DEFAULT_MANIFEST = REPO_ROOT / "analysis" / "manifests" / "payload_manifest.json"

SZ_MAGIC = b"7z\xbc\xaf\x27\x1c"
RCC_MAGIC = b"qres"

# Archives whose name can be sanity-checked by looking for a top-level entry.
CONTENT_HINTS = {
    "bearer": ["bearer/"],
    "iconengines": ["iconengines/"],
    "imageformats": ["imageformats/"],
    "platforminputcontexts": ["platforminputcontexts/"],
    "platforms": ["platforms/"],
    "qmltooling": ["qmltooling/"],
    "styles": ["styles/"],
    "translations": ["translations/"],
    "virtualkeyboard": ["virtualkeyboard/"],
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_pe(data: bytes) -> dict:
    """Return PE facts needed to locate the appended IFW region."""
    if data[:2] != b"MZ":
        raise ValueError("not a PE file (missing MZ header)")
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew : e_lfanew + 4] != b"PE\0\0":
        raise ValueError("not a PE file (missing PE signature)")
    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    opt_size = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    if magic == 0x20B:  # PE32+
        dd_off = opt + 112
    elif magic == 0x10B:  # PE32
        dd_off = opt + 96
    else:
        raise ValueError(f"unsupported optional header magic 0x{magic:04x}")
    cert_offset, cert_size = struct.unpack_from("<II", data, dd_off + 8 * 4)
    sections = opt + opt_size
    end_of_image = 0
    for i in range(num_sections):
        s = sections + 40 * i
        size_raw, ptr_raw = struct.unpack_from("<II", data, s + 16)
        end_of_image = max(end_of_image, ptr_raw + size_raw)
    return {
        "e_lfanew": e_lfanew,
        "num_sections": num_sections,
        "end_of_image": end_of_image,
        "cert_offset": cert_offset,
        "cert_size": cert_size,
    }


def verify_7z_at(mm: mmap.mmap, off: int, limit: int) -> dict | None:
    """If a valid 7z start header lives at *off*, return its size info."""
    hdr = bytes(mm[off : off + 32])
    if len(hdr) < 32 or hdr[:6] != SZ_MAGIC:
        return None
    (start_crc,) = struct.unpack_from("<I", hdr, 8)
    if zlib.crc32(hdr[12:32]) != start_crc:
        return None
    nh_off, nh_size, nh_crc = struct.unpack_from("<QQI", hdr, 12)
    if nh_size == 0:
        return None
    size = 32 + nh_off + nh_size
    if off + size > limit:
        return None
    nhdr = bytes(mm[off + 32 + nh_off : off + 32 + nh_off + nh_size])
    if len(nhdr) != nh_size or zlib.crc32(nhdr) != nh_crc:
        return None
    return {"size": size, "next_header_offset": nh_off, "next_header_size": nh_size}


def carve_archives(mm: mmap.mmap, start: int, end: int) -> list[dict]:
    """Sequentially carve every 7z archive between *start* and *end*."""
    archives: list[dict] = []
    pos = start
    while pos < end:
        off = mm.find(SZ_MAGIC, pos, end)
        if off < 0:
            break
        info = verify_7z_at(mm, off, end)
        if info is None:
            pos = off + 1  # stray magic, keep scanning
            continue
        archives.append({"offset": off, **info})
        pos = off + info["size"]
    return archives


def parse_updates_xml(mm: mmap.mmap, start: int, end: int) -> dict:
    """Pull the metadata we care about out of the embedded Updates.xml."""
    idx = mm.find(b"<DownloadableArchives>", start, end)
    if idx < 0:
        return {}
    window = bytes(mm[max(start, idx - 8192) : min(end, idx + 8192)])
    out: dict = {}
    m = re.search(rb"<ApplicationName>(.*?)</ApplicationName>", window)
    if m:
        out["application_name"] = m.group(1).decode("utf-8", "replace")
    m = re.search(rb"<ApplicationVersion>(.*?)</ApplicationVersion>", window)
    if m:
        out["application_version"] = m.group(1).decode("utf-8", "replace")
    m = re.search(
        rb"<UpdateFile[^>]*CompressedSize=\"(\d+)\"[^>]*UncompressedSize=\"(\d+)\"", window
    )
    if m:
        out["declared_compressed_size"] = int(m.group(1))
        out["declared_uncompressed_size"] = int(m.group(2))
    m = re.search(rb"<DownloadableArchives>(.*?)</DownloadableArchives>", window, re.S)
    if m:
        out["downloadable_archives"] = [
            name.strip()
            for name in m.group(1).decode("utf-8", "replace").split(",")
            if name.strip()
        ]
    start_xml = window.find(b"<?xml")
    if start_xml >= 0:
        end_xml = window.find(b"</Updates>")
        if end_xml > 0:
            out["updates_xml"] = window[start_xml : end_xml + len(b"</Updates>")].decode(
                "utf-8", "replace"
            )
    return out


def seven_zip(*args: str, timeout: int = 1800) -> subprocess.CompletedProcess:
    return subprocess.run(["7z", *args], capture_output=True, text=True, timeout=timeout)


def list_entries(archive: Path, limit: int = 12) -> list[str]:
    proc = seven_zip("l", "-slt", str(archive))
    if proc.returncode != 0:
        return []
    paths = re.findall(r"^Path = (.+)$", proc.stdout, re.M)
    return paths[1 : limit + 1]  # first entry is the archive itself


def test_archive(archive: Path) -> tuple[bool, str]:
    proc = seven_zip("t", str(archive))
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    summary = lines[-1] if lines else proc.stderr.strip()
    return proc.returncode == 0, summary


def extract_archive(archive: Path, dest: Path) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    proc = seven_zip("x", "-y", f"-o{dest}", "--", str(archive))
    return proc.returncode == 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Statically extract the payload of a Qt IFW installer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--installer", type=Path, default=DEFAULT_INSTALLER)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--no-extract", action="store_true", help="carve + validate only")
    args = ap.parse_args(argv)

    installer: Path = args.installer
    if not installer.is_file():
        print(f"error: installer not found: {installer}", file=sys.stderr)
        return 2

    with installer.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        file_size = mm.size()
        e_lfanew = struct.unpack_from("<I", bytes(mm[:0x40]), 0x3C)[0]
        pe = parse_pe(bytes(mm[: e_lfanew + 0x1000]))
        start = pe["end_of_image"]
        end = pe["cert_offset"] if pe["cert_size"] else file_size
        if not (0 < start < end <= file_size):
            print("error: implausible appended-region layout", file=sys.stderr)
            return 2
        print(f"installer : {installer.name} ({file_size:,} bytes)")
        print(f"region    : [0x{start:X}, 0x{end:X})  size={end - start:,} bytes")
        print(f"cert      : size={pe['cert_size']:,} @0x{end:X}")
        archives = carve_archives(mm, start, end)
        meta_blob = bytes(mm[start : archives[0]["offset"]]) if archives else b""
        updates = parse_updates_xml(mm, start, end)

    print(f"meta blob : {len(meta_blob):,} bytes, magic={meta_blob[:4]!r}")
    print(f"archives  : {len(archives)} carved")

    names = updates.get("downloadable_archives", [])
    if len(names) != len(archives):
        print(f"warning   : Updates.xml lists {len(names)} archives, {len(archives)} carved")
        names = [f"archive_{i:02d}" for i in range(len(archives))]

    payload_dir = args.out / "payload"
    meta_dir = args.out / "meta"
    payload_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    if meta_blob[:4] == RCC_MAGIC:
        (meta_dir / "resources.rcc").write_bytes(meta_blob)
    if updates.get("updates_xml"):
        (meta_dir / "Updates.xml").write_text(updates["updates_xml"], encoding="utf-8")

    manifest: dict = {
        "installer": {
            "path": str(installer),
            "size": file_size,
            "sha256": sha256_file(installer),
        },
        "region": {
            "start": start,
            "end": end,
            "size": end - start,
            "meta_blob_size": len(meta_blob),
            "meta_magic": meta_blob[:4].decode("ascii", "replace"),
        },
        "updates_xml": {k: v for k, v in updates.items() if k != "updates_xml"},
        "archives": [],
        "warnings": [],
    }

    ok_count = 0
    with installer.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        for i, (name, info) in enumerate(zip(names, archives)):
            blob = bytes(mm[info["offset"] : info["offset"] + info["size"]])
            archive_path = payload_dir / name
            archive_path.write_bytes(blob)
            digest = hashlib.sha256(blob).hexdigest()
            entries = list_entries(archive_path)
            tested, summary = test_archive(archive_path)
            ok_count += int(tested)
            stem = name[:-3] if name.endswith(".7z") else name
            hint_ok: bool | None = None
            if stem in CONTENT_HINTS and entries:
                hint_ok = any(
                    any(e.startswith(hint) for e in entries) for hint in CONTENT_HINTS[stem]
                )
                if not hint_ok:
                    manifest["warnings"].append(f"{name}: content does not match the name hint")
            confidence = "positional+content" if hint_ok else (
                "positional" if hint_ok is None else "positional(mismatch)"
            )
            entry = {
                "index": i,
                "name": name,
                "offset": info["offset"],
                "size": info["size"],
                "sha256": digest,
                "integrity_ok": tested,
                "integrity_summary": summary,
                "name_confidence": confidence,
                "first_entries": entries[:8],
            }
            if not args.no_extract and tested:
                entry["extracted"] = extract_archive(archive_path, payload_dir / stem)
            manifest["archives"].append(entry)
            print(
                f"  [{i:02d}] {name:<26} {info['size']:>12,} B @0x{info['offset']:09X} "
                f"test={'ok' if tested else 'FAIL'} extract={entry.get('extracted', '-')}"
            )

    total = sum(a["size"] for a in manifest["archives"])
    manifest["totals"] = {
        "archives": len(manifest["archives"]),
        "archives_integrity_ok": ok_count,
        "carved_bytes": total,
    }
    declared = updates.get("declared_compressed_size")
    if declared is not None:
        manifest["totals"]["declared_compressed_size"] = declared
        manifest["totals"]["declared_size_delta"] = total - declared
        if abs(total - declared) > 2 * 1024 * 1024:
            manifest["warnings"].append(
                f"carved total {total:,} differs from declared {declared:,} by "
                f"{total - declared:,} bytes"
            )

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"\ntotal carved: {total:,} bytes; integrity ok: {ok_count}/{len(archives)}")
    print(f"manifest    : {args.manifest}")
    for warning in manifest["warnings"]:
        print(f"warning     : {warning}")
    return 0 if ok_count == len(archives) else 1


if __name__ == "__main__":
    raise SystemExit(main())


