# Original artifact: "A HUB_Game_Win_V1.0.19.exe"

This file documents the immutable reference artifact that this project's
reverse-engineering work is based on. **Do not modify, rename or delete it.**

| Property | Value |
|---|---|
| Filename | `A HUB_Game_Win_V1.0.19.exe` |
| Size | 346 504 864 bytes (330.4 MiB) |
| MD5 | `61047880b93efc981a287d61850d1440` |
| SHA-256 | `ebf741e0aa0fbd480dd10870d982457c29521c7d8681b995f7ade4bc01c1ac01` |
| Format | PE32+ x86-64 console executable, Qt Installer Framework 4.6.1 (built with Qt 5.15.2) |
| Product | Rapoo "A HUB" 1.0.19 (package id `com.rapood.rapoodriver`, build dated 2026-06-03) |

Verify the integrity of the artifact at any time:

```bash
./tools/verify_original.sh
```

## Internal structure (as reverse engineered)

The installer is a Qt Installer Framework (IFW) **offline** installer. Its
layout, determined without executing it:

```
[0x00000000 .. 0x01857000)   PE image (installer stub, 25 710 592 bytes) + PE overhead
[0x01857000 .. 0x14A71498)   Appended IFW binary content (320 968 856 bytes)
                             ├── compiled Qt resource blob "qres" (meta: config.xml,
                             │   installscript.qs, Updates.xml, icons, ~31 KB)
                             └── 20 concatenated `7z` archives (see manifest)
[0x14A71498 .. 0x14A714A0)   (padding; region end)
[0x14A71498 .. end)          Authenticode certificate (10 760 bytes)
```

- The payload archives are listed in `Updates.xml`
  (`Updates.xml → PackageUpdate → DownloadableArchives`):
  `bearer.7z, default.7z, iconengines.7z, imageformats.7z, lib.7z,
  platforminputcontexts.7z, platforms.7z, qmltooling.7z, Qt.7z, QtCharts.7z,
  QtGraphicalEffects.7z, QtQml.7z, QtQuick.7z, QtQuick.2.7z, QtWinExtras.7z,
  resources.7z, styles.7z, translations.7z, virtualkeyboard.7z, content.7z`
- Declared sizes: 320 937 219 bytes compressed / 480 534 711 bytes uncompressed.
- `content.7z` contains the Rapoo application itself; the rest are Qt 5.15.2
  runtime components.

Extraction is performed offline and read-only with:

```bash
python3 tools/ifw_extract.py            # writes analysis/extracted/ + analysis/manifests/
```

## Safety rules

1. This artifact is treated as **read-only input**. No tool in this repository
   writes to it; `tools/verify_original.sh` is run to prove it stayed intact.
2. Extracted content (`analysis/extracted/`) is proprietary Rapoo material.
   It is git-ignored, must not be redistributed, and is used solely for
   interoperability analysis of a device owned by the user.
