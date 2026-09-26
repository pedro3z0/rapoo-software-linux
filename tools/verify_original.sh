#!/usr/bin/env bash
# Verify that the original Rapoo Windows driver installer is byte-identical to
# the artifact this repository was reverse engineered from.
#
# Usage: ./tools/verify_original.sh [path/to/installer.exe]
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(dirname "$HERE")"
FILE="${1:-$ROOT/A HUB_Game_Win_V1.0.19.exe}"

EXPECTED_SIZE=346504864
EXPECTED_MD5="61047880b93efc981a287d61850d1440"
EXPECTED_SHA256="ebf741e0aa0fbd480dd10870d982457c29521c7d8681b995f7ade4bc01c1ac01"

fail() { echo "FAIL: $*" >&2; exit 1; }

[[ -f "$FILE" ]] || fail "installer not found: $FILE"

size=$(stat -c%s "$FILE")
[[ "$size" == "$EXPECTED_SIZE" ]] || fail "size mismatch: got $size, expected $EXPECTED_SIZE"

md5=$(md5sum "$FILE" | cut -d' ' -f1)
[[ "$md5" == "$EXPECTED_MD5" ]] || fail "md5 mismatch: got $md5, expected $EXPECTED_MD5"

sha256=$(sha256sum "$FILE" | cut -d' ' -f1)
[[ "$sha256" == "$EXPECTED_SHA256" ]] || fail "sha256 mismatch: got $sha256, expected $EXPECTED_SHA256"

echo "OK: $FILE"
echo "    size=$(printf '%d' "$size")"
echo "    md5=$md5"
echo "    sha256=$sha256"
echo "    artifact is byte-identical to the reference."
