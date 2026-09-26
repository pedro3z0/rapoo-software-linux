# Supported Rapoo Devices & Compatibility Matrix

This project dynamically queries its hardware database extracted from official Rapoo specifications
(`analysis/manifests/official_web_models.json`). Over **100 Rapoo peripheral models** are mapped,
sharing the same underlying firmware protocol architecture (nRF54L / Telink / Bolutek).

---

## Verified Devices

| Model | Dongle VID:PID | Wired VID:PID | MCU | Sensor | Polling Rates Supported | Notes |
|---|---|---|---|---|---|---|
| **Rapoo VT3 Air / VT0 Air MAX** | `24AE:14A1` | `24AE:46A1` | N54L15 | PAW3950U | 125Hz - 8000Hz | Primary target hardware. 300mAh battery. |
| **Rapoo VT3S Air Max** | `24AE:14A2` | `24AE:46A2` | N54L15 | PAW3950U | 125Hz - 8000Hz | Nordic L5 dongle |
| **Rapoo VT3 PRO V2** | `24AE:14A5` | `24AE:46A5` | N54L15 | PAW3955U | 125Hz - 8000Hz | Nordic L5 dongle |
| **Rapoo VT3S PRO V2** | `24AE:14A6` | `24AE:46A6` | N54L15 | PAW3955U | 125Hz - 8000Hz | Nordic L5 dongle |
| **Rapoo VT3 MAX** | `24AE:1417` | `24AE:4617` | N54L15 | PAW3950U | 125Hz - 8000Hz | 800mAh battery |
| **Rapoo VT3 MAX V2** | `24AE:1B06` | `24AE:4B06` | N54LM20 | PAW3955U | 125Hz - 8000Hz | Nordic LM20 dongle |
| **Rapoo VT3 MAX MASTER V2** | `24AE:146D` | `24AE:466D` | N54H20 | PAW3955U | 125Hz - 8000Hz | Nordic H20 dongle |
| **Rapoo VT7 PRO V2** | `24AE:14A7` | `24AE:46A7` | N54L15 | PAW3955U | 125Hz - 8000Hz | Nordic L5 dongle |
| **Rapoo VT7S PRO V2** | `24AE:14A8` | `24AE:46A8` | N54L15 | PAW3955U | 125Hz - 8000Hz | Nordic L5 dongle |
| **Rapoo VT9 PRO V2** | `24AE:14A9` | `24AE:46A9` | N54L15 | PAW3955U | 125Hz - 8000Hz | Nordic L5 dongle |
| **Rapoo VT9 Air MAX V2** | `24AE:1B10` | `24AE:4B10` | N54LM20 | PAW3955U | 125Hz - 8000Hz | Nordic LM20 dongle |
| **Rapoo VT0** | `24AE:1410` | `24AE:4610` | N54L15 | PAW3398 | 125Hz - 1000Hz | Standard tier |
| **Rapoo VT0 MAX** | `24AE:1420` | `24AE:4620` | N54L15 | PAW3950U | 125Hz - 8000Hz | Retail tier |

---

## Rapoo Web Interface Compatibility

Rapoo provides an official WebHID interface at `https://hub.rapoo.cn/`.
Because this project configures the standard Linux `udev` rules (`99-rapoo.rules`), **you can also
open Chrome / Edge / Chromium and use Rapoo's official Web Driver directly on Linux!**

Both this open-source tool and Rapoo's official web driver can configure the mouse without conflict.
