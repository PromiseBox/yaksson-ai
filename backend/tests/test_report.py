"""
v3 리포트 레이어 회귀 테스트 — 출력 포맷·결측문구·이상여부(환각/금지어/출처). [근일]
실데이터 없이 Mock으로 검증한다. CI에서 항상 통과해야 한다.
"""
from __future__ import annotations

from agents import comm, risk
from agents.assemble import BANNED, audit_report, build_report
from domain.models import FlagType, PatientProfile, Severity, Source
from domain.report import ReportItem, ReportMeta, ReportPayload
from tools.datasource import MockDataSource
from tools.mock_data import find_drug_by_name


def _state(names: list[str], age: int = 72, pregnant: bool = False) -> dict:
    """8노드 대신, 동일 정규화 모델로 state(profile+conflicts)를 구성."""
    p = PatientProfile(profile_id="t", alias="아버지", age=age, is_pregnant=pregnant)
    for n in names:
        d = find_drug_by_name(n)
        assert d is not None, f"골든 카탈로그에 {n} 없음"
        p.drugs.append(d)
    conflicts = risk.analyze(p, MockDataSource())
    return {
        "profile": p,
        "conflicts": conflicts,
        "needs_pharmacist": any(c.severity == Severity.HIGH for c in conflicts),
    }


# ---------- 포맷 & 사실 필드 ----------
def test_byungyong_report_basic():
    r = build_report(_state(["가나정", "다라캡슐"]))
    assert isinstance(r, ReportPayload)
    assert r.items, "병용금기 항목이 있어야 함"
    assert r.counts["위험"] >= 1
    assert r.needs_pharmacist is True
    # 출처 인용률 100% (모든 항목에 source.provider)
    assert all(it.source and it.source.provider for it in r.items)
    assert r.eval_report["report_audit"]["source_rate"] == 1.0
    # 서술(GPT-5.5/템플릿) 채워짐
    assert r.overall_message
    assert all(it.easy_explanation and it.question_for_pharmacist for it in r.items)
    # 이상 없음
    assert r.eval_report["report_audit"]["passed"] is True


def test_grade_and_sort_severity():
    r = build_report(_state(["가나정", "다라캡슐", "벤조원정"], age=76))
    grades = [it.grade for it in r.items]
    assert grades[0] == "위험"  # 상이 먼저
    assert any("치매·낙상 위험" in it.tags for it in r.items)  # 고위험 PIM 태그


def test_no_conflicts_normal():
    r = build_report(_state(["마바정"], age=40))  # 노인주의는 고령에서만 → 비고령은 0건
    assert r.items == []
    assert r.counts["정상"] == 1
    assert r.needs_pharmacist is False
    assert "발견되지 않았습니다" in r.overall_message
    assert r.eval_report["report_audit"]["passed"] is True


# ---------- 결측 사유 표준문구 (기획서 §4.5) ----------
def test_fill_reason_standard_phrase():
    assert comm.fill_reason("노인주의", "") == comm.STANDARD_PHRASES["노인주의"]
    assert comm.fill_reason("효능군중복", "   ") == comm.STANDARD_PHRASES["효능군중복"]
    assert comm.fill_reason("노인주의", "구체 사유") == "구체 사유"  # 있으면 그대로


# ---------- 이상여부 검증 ----------
def _payload_with(expl: str) -> ReportPayload:
    it = ReportItem(
        severity=Severity.HIGH, grade="위험", flag_type=FlagType.USJNT_TABOO,
        drugs=["가나정"], reason="x", source=Source(operation="op"),
        easy_explanation=expl, question_for_pharmacist="약사에게 확인해 주세요",
    )
    return ReportPayload(meta=ReportMeta(alias="t"), items=[it])


def test_audit_catches_hallucination():
    a = audit_report(_payload_with("엉뚱한약물정 때문에 위험합니다"), allowed_drugs={"가나정"})
    assert a["passed"] is False
    assert a["hallucination_free"] is False


def test_audit_catches_banned_word():
    a = audit_report(_payload_with("이 약을 중단하세요"), allowed_drugs={"가나정"})
    assert a["passed"] is False
    assert any("금지어" in x for x in a["issues"])


def test_audit_allows_profile_drug():
    a = audit_report(_payload_with("가나정은 함께 복용 시 주의가 필요해요"), allowed_drugs={"가나정"})
    assert a["passed"] is True


def test_audit_allows_real_drug_name_with_suffix():
    # 실제 약명은 숫자/괄호/제형 suffix가 붙음(예: '테고캡슐20') → 부분일치로 환각 오탐 안 함
    ok = audit_report(_payload_with("테고캡슐20은 함께 복용 시 주의가 필요해요"),
                      allowed_drugs={"테고캡슐20"})
    assert ok["passed"] is True
    assert ok["hallucination_free"] is True
    # 단, 진짜 프로필 외 약명은 여전히 환각으로 탐지
    bad = audit_report(_payload_with("아스피린정도 있어요"), allowed_drugs={"테고캡슐20"})
    assert bad["hallucination_free"] is False


def test_audit_no_false_positive_on_caution_word():
    # 'X주의'(注意: 투여기간주의/용량주의/노인주의)가 약 접미사 '주'로 오탐되지 않아야 함
    a = audit_report(_payload_with("투여기간주의 항목으로 등재되어 있습니다"),
                     allowed_drugs={"가나정"})
    assert a["hallucination_free"] is True


def test_no_banned_words_in_generated_report():
    r = build_report(_state(["가나정", "다라캡슐", "벤조원정"], age=76))
    for it in r.items:
        assert not BANNED.search(it.easy_explanation)
        assert not BANNED.search(it.question_for_pharmacist)
    assert not BANNED.search(r.overall_message)
