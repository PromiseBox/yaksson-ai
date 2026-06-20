"""
약손 AI — 리포트 출력 포맷 (프론트가 그대로 렌더하는 고정 JSON 계약). [근일]

설계 원칙:
- 사실 필드(규칙엔진/DB에서 옴): severity·grade·flag_type·drugs·reason·source·tags·recommendation
  → 코드가 채우며 LLM이 바꾸지 못한다.
- 서술 필드(GPT-5.5 생성): overall_message·easy_explanation·question_for_pharmacist
  → '말투'만 입힌다. (세 안전장치: 환각 제로 / 출처 있는 판정 / 진단 금지 라우팅)
- 식약처 필드가 변해도 이 계약은 불변 → 프론트/백엔드 분리(기획서 §11.2). schema_version으로 버전 고정.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from domain.models import FlagType, Severity, Source

SCHEMA_VERSION = "1.0"

# 심각도 → 보호자 화면 3등급 라벨 (기획서 §7.3 / PPT slide 8: 위험·주의·정상)
GRADE_BY_SEVERITY: dict[Severity, str] = {
    Severity.HIGH: "위험",
    Severity.MEDIUM: "주의",
    Severity.LOW: "주의",
}


class ReportMeta(BaseModel):
    alias: str = "어르신"
    age: int | None = None
    drug_count: int = 0
    checked_at: str = ""  # ISO8601 (YYYY-MM-DD)
    data_provider: str = "식품의약품안전처 DUR(의약품안전사용서비스)"
    disclaimer: str = (
        "본 리포트는 진단·처방이 아닌 보조 참고 수단입니다. "
        "복용 중단·변경은 반드시 약사·의사와 상의하세요."
    )


class ReportItem(BaseModel):
    """위험 카드 1건. 화면에 그대로 노출되는 단위."""

    # --- 사실(규칙엔진) : LLM이 변경 불가 ---
    severity: Severity
    grade: str = ""  # 위험/주의 (severity에서 파생된 UI 라벨)
    flag_type: FlagType
    drugs: list[str] = Field(default_factory=list)
    reason: str = ""  # prohibit_content 또는 결측 시 §4.5 표준문구
    source: Source = Field(default_factory=Source)
    tags: list[str] = Field(default_factory=list)  # 예: ["치매·낙상 위험"]
    recommendation: str = ""

    # --- 서술(GPT-5.5) ---
    easy_explanation: str = ""
    question_for_pharmacist: str = ""


class ReportPayload(BaseModel):
    """/analyze 응답 = 프론트 렌더 계약."""

    schema_version: str = SCHEMA_VERSION
    meta: ReportMeta
    overall_message: str = ""  # 보호자용 한 단락 요약(GPT-5.5)
    counts: dict[str, int] = Field(default_factory=dict)  # {"위험":n,"주의":n,"정상":n}
    needs_pharmacist: bool = False  # 심각도 '상' 존재 → Gate(약사 라우팅)
    items: list[ReportItem] = Field(default_factory=list)  # 위험도순 정렬
    questions: list[str] = Field(default_factory=list)  # 약사 질문지(전체)
    schedule: dict[str, list[str]] = Field(default_factory=dict)  # 아침/점심/저녁
    intervention_note: str = ""  # 약사 인계용 중재의견서(마크다운)
    eval_report: dict = Field(default_factory=dict)  # 출처/환각/금지어 검증 결과
