# -*- coding: utf-8 -*-
"""Rapoo Device Registry - Database of Rapoo devices and capabilities.
Derived from extracted driver manifests and official Rapoo Web driver specifications.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Optional, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MANIFEST_PATH = REPO_ROOT / "analysis" / "manifests" / "official_web_models.json"



# Sensor engine scan-rate label per USB PID (both wired + dongle PIDs),
# extracted from the official WebHID driver device table (80 models /
# 152 PIDs, 2026-10-14). Drives the
# ">=NKFPS engine scan rate" preset copy. Models without the capability
# (keyboards, legacy tiers) simply have no entry.
SENSOR_SCAN_LABELS: Dict[int, str] = {}
for _pid in [5136, 5137, 5138, 5139, 5140, 5141, 5154, 5188, 5201, 17936, 17937, 17938, 17939, 17940, 17941, 17954, 17969, 17970, 17971, 17973, 17988, 18001]:
    SENSOR_SCAN_LABELS[_pid] = "10K"
for _pid in [5142, 5143, 5144, 5152, 5153, 5155, 5194, 5195, 5202, 5203, 5209, 5211, 5213, 5216, 5218, 5220, 5222, 5224, 5226, 5228, 5229, 5230, 5232, 5233, 5234, 5235, 5236, 5237, 5238, 5239, 5240, 5281, 5282, 5284, 5285, 5286, 5287, 5288, 5289, 5290, 6913, 6914, 6915, 6916, 6917, 6918, 6919, 6920, 6921, 6922, 6923, 6924, 6925, 6926, 6927, 6928, 6929, 6930, 6931, 6932, 6933, 6944, 6945, 17942, 17943, 17944, 17952, 17953, 17955, 17975, 17984, 17994, 17995, 17997, 18002, 18003, 18009, 18011, 18013, 18016, 18018, 18020, 18022, 18024, 18026, 18028, 18029, 18030, 18032, 18033, 18034, 18035, 18036, 18037, 18038, 18039, 18040, 18049, 18081, 18082, 18084, 18085, 18086, 18087, 18088, 18089, 18090, 19201, 19202, 19203, 19204, 19205, 19206, 19207, 19208, 19209, 19210, 19211, 19212, 19213, 19214, 19215, 19216, 19217, 19218, 19219, 19220, 19221, 19232, 19233]:
    SENSOR_SCAN_LABELS[_pid] = "13K"


@dataclass
class DeviceModel:
    model: str
    pids: List[int]
    mcu: str = ""
    sensor: str = ""
    driver: str = ""
    dongle: str = ""
    battery: int = 0
    sensor_scan_label: str = ""
    capabilities: Dict[str, Any] = field(default_factory=dict)

    def matches_pid(self, pid: int) -> bool:
        return pid in self.pids


class DeviceRegistry:
    def __init__(self):
        self._models: List[DeviceModel] = []
        self._load()

    def _load(self):
        if not MANIFEST_PATH.is_file():
            # Fallback default definitions if manifest json is missing
            self._models.append(DeviceModel(
                model="VT0 Air MAX / VT3 Air",
                pids=[18081, 5281],  # 0x46A1, 0x14A1
                mcu="N54L15",
                sensor="PAW3950U",
                driver="VT_nrf54L",
                dongle="Dongle_NordicL5",
                battery=300
            ))
            return

        with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            for item in data:
                model_pids = item.get("pids", [])
                self._models.append(DeviceModel(
                    model=item.get("model", ""),
                    pids=model_pids,
                    mcu=item.get("mcu", ""),
                    sensor=item.get("sensor", ""),
                    driver=item.get("driver", ""),
                    dongle=item.get("dongle", ""),
                    battery=item.get("battery", 0),
                    sensor_scan_label=next(
                        (SENSOR_SCAN_LABELS[pid] for pid in model_pids if pid in SENSOR_SCAN_LABELS),
                        "",
                    ),
                ))

    def find_by_pid(self, pid: int) -> Optional[DeviceModel]:
        for model in self._models:
            if model.matches_pid(pid):
                return model
        return None

    def all_models(self) -> List[DeviceModel]:
        return list(self._models)


registry = DeviceRegistry()

