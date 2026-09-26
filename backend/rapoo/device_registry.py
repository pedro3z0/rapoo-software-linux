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


@dataclass
class DeviceModel:
    model: str
    pids: List[int]
    mcu: str = ""
    sensor: str = ""
    driver: str = ""
    dongle: str = ""
    battery: int = 0
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
                self._models.append(DeviceModel(
                    model=item.get("model", ""),
                    pids=item.get("pids", []),
                    mcu=item.get("mcu", ""),
                    sensor=item.get("sensor", ""),
                    driver=item.get("driver", ""),
                    dongle=item.get("dongle", ""),
                    battery=item.get("battery", 0)
                ))

    def find_by_pid(self, pid: int) -> Optional[DeviceModel]:
        for model in self._models:
            if model.matches_pid(pid):
                return model
        return None

    def all_models(self) -> List[DeviceModel]:
        return list(self._models)


registry = DeviceRegistry()

