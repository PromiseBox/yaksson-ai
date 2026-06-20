"""
약손 AI — 리포트 조립 + 출력 이상여부 검증. [근일]

흐름: state(8노드 결과) → ReportItem(사실) 채움 → comm.generate_narration(서술)
      → audit_report(환각/금지어/출처) → 실패 시 템플릿으로 안전 폴백 → ReportPayload.

이 모듈은 DataSource 종류(Mock/Pg)를 모른다. 오직 정규화 모델(Conflict/Source)만 본다.
→ 성빈의 PgDataSource가 붙어도 이 파일은 바뀌지 않는다.
"""
from __future__ import annotations

import re
from datetime import date

from agents import comm
from domain.models import Conflict, PatientProfile, Severity
from domain.report import GRADE_BY_SEVERITY, ReportItem, ReportMeta, ReportPayload

# 진단·처방 단정 금지어 (세 안전장치 ③ 진단 금지 라우팅)
BANNED = re.compile(
    r"(중단|복용\s*중지|끊으세요|끊으십시오|증량|감량|줄이세요|늘리세요|처방받|진단)"
)

# 약명 후보(휴리스틱): …정/캡슐/시럽/주/액/산. 흔한 일반어는 _STOP으로 제외.
# NOTE: 운영에서는 정규화된 약명 사전(기획서 §4.7 alias 사전)으로 대체 권장.
_DRUGLIKE = re.compile(r"[가-힣A-Za-z0-9]{1,12}(?:정|캡슐|연질캡슐|시럽|시럽제|주|액|산)")
_STOP = {
    "진정", "안정", "측정", "결정", "조정", "확정", "추정", "인정", "특정", "예정",
    "일정", "가정", "감정", "수정", "선정", "설정", "지정", "규정", "부정", "긍정",
    "교정", "개정", "재정", "행정", "법정", "보정", "공정", "과정", "주정",
    "계산", "생산", "재산", "예산", "해산", "출산", "유산", "자산",
}


def _counts(profile: PatientProfile, conflicts: list[Conflict]) -> dict[str, int]:
    """위험(상)/주의(중·하)/정상(충돌 없는 약) 건수."""
    high = sum(1 for c in conflicts if c.severity == Severity.HIGH)
    mid_low = sum(1 for c in conflicts if c.severity != Severity.HIGH)
    flagged = {d for c in conflicts for d in c.drugs}
    normal = sum(1 for d in profile.drugs if d.name not in flagged)
    return {"위험": high, "주의": mid_low, "정상": normal}


def build_report(state: dict) -> ReportPayload:
    """8노드 실행 결과(state)를 프론트용 ReportPayload로 조립."""
    profile: PatientProfile = state["profile"]
    conflicts: list[Conflict] = list(state.get("conflicts") or [])

    items: list[ReportItem] = [
        ReportItem(
            severity=c.severity,
            grade=GRADE_BY_SEVERITY.get(c.severity, "주의"),
            flag_type=c.flag_type,
            drugs=list(c.drugs),
            reason=comm.fill_reason(c.flag_type.value, c.reason),  # §4.5 결측 처리
            source=c.source,
            tags=list(c.tags),
            recommendation=c.recommendation,
        )
        for c in conflicts
    ]

    payload = ReportPayload(
        meta=ReportMeta(
            alias=profile.alias,
            age=profile.age,
            drug_count=len(profile.drugs),
            checked_at=date.today().isoformat(),
        ),
        counts=_counts(profile, conflicts),
        needs_pharmacist=bool(
            state.get("needs_pharmacist")
            or any(c.severity == Severity.HIGH for c in conflicts)
        ),
        items=items,
        questions=list(state.get("questions") or []),
        schedule=dict(state.get("schedule") or {}),
        intervention_note=state.get("intervention_note", "") or "",
    )

    # 서술(프롬프트 → 설명) 생성: GPT-5.5 또는 템플릿 폴백
    comm.generate_narration(payload)

    # 이상여부 검증 → 실패 시 전체 서술을 안전 템플릿으로 강등 후 재검증
    allowed = {d.name for d in profile.drugs}
    audit = audit_report(payload, allowed)
    if not audit["passed"]:
        _sanitize(payload)
        audit = audit_report(payload, allowed)

    merged = dict(state.get("eval_report") or {})  # 기존 eval_node 결과 보존
    merged["report_audit"] = audit
    payload.eval_report = merged
    return payload


def _druglike_tokens(text: str) -> set[str]:
    return {t for t in _DRUGLIKE.findall(text or "") if t not in _STOP}


def audit_report(payload: ReportPayload, allowed_drugs: set[str]) -> dict:
    """GPT-5.5 출력 이상여부 점검: 환각 약물 / 금지어 / 출처 누락."""
    issues: list[str] = []
    for i, it in enumerate(payload.items):
        for field_name, text in (
            ("easy_explanation", it.easy_explanation),
            ("question", it.question_for_pharmacist),
        ):
            for tok in _druglike_tokens(text):
                if tok not in allowed_drugs:  # 1) 프로필 외 약물 = 환각
                    issues.append(f"item{i}.{field_name}: 프로필 외 약명 후보 '{tok}'")
            if BANNED.search(text or ""):  # 3) 금지어
                issues.append(f"item{i}.{field_name}: 진단·처방 금지어")
        if not (it.source and it.source.provider):  # 4) 출처 누락
            issues.append(f"item{i}: 출처 누락")

    if BANNED.search(payload.overall_message or ""):
        issues.append("overall: 진단·처방 금지어")
    for tok in _druglike_tokens(payload.overall_message):
        if tok not in allowed_drugs:
            issues.append(f"overall: 프로필 외 약명 후보 '{tok}'")

    n = max(len(payload.items), 1)
    cited = sum(1 for it in payload.items if it.source and it.source.provider)
    return {
        "passed": not issues,
        "issues": issues,
        "source_rate": round(cited / n, 4),
        "hallucination_free": not any("프로필 외 약명" in x for x in issues),
        "item_count": len(payload.items),
    }


def _sanitize(payload: ReportPayload) -> None:
    """이상 발견 시 전체 서술을 안전한 템플릿으로 재생성(사실 필드는 불변)."""
    for it in payload.items:
        it.easy_explanation = ""
        it.question_for_pharmacist = ""
    payload.overall_message = ""
    comm._template_narration(payload)
