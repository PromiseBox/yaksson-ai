"""
메모리 (Memory Agent) — 가족 구성원별 약물 프로필 저장 + 재방문 시 변경 비교.

MVP: 프로세스 내 dict + JSON 파일 백업. 운영: PostgreSQL+pgvector 로 교체(역할 C).
'stateful'을 트랙2에 보여주는 핵심: 같은 어르신을 다시 열면 이전 약과의 차이만 부각한다.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from domain.models import PatientProfile

_STORE_PATH = Path(__file__).resolve().parent.parent / "data_store.json"


def _load() -> dict[str, Any]:
    if _STORE_PATH.exists():
        return json.loads(_STORE_PATH.read_text(encoding="utf-8"))
    return {}


def _save(store: dict[str, Any]) -> None:
    _STORE_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


def load_previous(profile_id: str) -> PatientProfile | None:
    store = _load()
    data = store.get(profile_id)
    return PatientProfile(**data) if data else None


def save_profile(profile: PatientProfile) -> None:
    store = _load()
    store[profile.profile_id] = profile.model_dump()
    _save(store)


def diff_drugs(prev: PatientProfile | None, curr: PatientProfile) -> dict[str, Any]:
    if prev is None:
        return {"first_visit": True, "added": [d.name for d in curr.drugs], "removed": []}
    prev_names = {d.name for d in prev.drugs}
    curr_names = {d.name for d in curr.drugs}
    return {
        "first_visit": False,
        "added": sorted(curr_names - prev_names),
        "removed": sorted(prev_names - curr_names),
    }
