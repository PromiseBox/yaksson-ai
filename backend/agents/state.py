"""
LangGraph 워크플로우 상태.

노드들은 (state) -> dict(부분 업데이트) 형태로 동작한다.
TypedDict(total=False)이므로 각 노드는 자신이 채우는 키만 반환하면 병합된다.
"""
from __future__ import annotations

from typing import Any, TypedDict

from domain.models import Conflict, DurRecord, PatientProfile


class PatientState(TypedDict, total=False):
    # 입력
    raw_input: str                         # 보호자가 입력한 원문(약명 나열 등)
    profile: PatientProfile                # 정규화된 환자/약 프로필

    # 처리 산출물
    records_by_drug: dict[str, list[DurRecord]]
    conflicts: list[Conflict]

    # 보호자용 출력
    summary: str                           # 쉬운 말 요약
    questions: list[str]                   # 약사에게 물어볼 질문
    schedule: dict[str, list[str]]         # 시간대 -> 약 이름들 (간이 복약표)

    # 게이트/평가/메모리
    needs_pharmacist: bool                 # 심각도 '상' 존재 시 True
    eval_report: dict[str, Any]            # 출처/환각 검증 결과
    memory_diff: dict[str, Any]            # 직전 프로필 대비 변경

    # v2 필드
    intervention_note: str                 # 약사 인계용 중재의견서 초안
    qr_path: str                           # QR PNG 경로 (없으면 None)
    qr_payload: dict                       # QR에 담긴 안전 프로필 payload
    new_conflicts: list                    # Delta: 이번 방문에서 새로 생긴 위험
