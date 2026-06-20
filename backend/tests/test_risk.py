"""
핵심 로직 테스트 — 위험 판정 엔진과 품질 검증.
실데이터 없이 골든 데이터로 검증되며, CI에서 항상 통과해야 한다.
"""
from __future__ import annotations

from agents import nodes, risk
from agents.state import PatientState
from domain.models import FlagType, PatientProfile, Severity
from tools.datasource import MockDataSource
from tools.mock_data import find_drug_by_name


def _profile(names, age=72, pregnant=False, pid="t"):
    p = PatientProfile(profile_id=pid, alias="아버지", age=age, is_pregnant=pregnant)
    for n in names:
        d = find_drug_by_name(n)
        assert d is not None, f"골든 카탈로그에 {n} 없음"
        p.drugs.append(d)
    return p


def test_detects_co_admin_taboo_high():
    """가나정 + 다라캡슐 = 병용금기(상) 1건, 양방향 중복 없이."""
    ds = MockDataSource()
    p = _profile(["가나정", "다라캡슐"])
    conflicts = risk.analyze(p, ds)
    taboo = [c for c in conflicts if c.flag_type == FlagType.USJNT_TABOO]
    assert len(taboo) == 1
    assert taboo[0].severity == Severity.HIGH
    assert set(taboo[0].drugs) == {"가나정", "다라캡슐"}
    assert taboo[0].source.provider  # 출처 필수


def test_no_false_positive_when_partner_absent():
    """다라캡슐 없이 가나정만 있으면 병용금기는 잡히면 안 된다."""
    ds = MockDataSource()
    p = _profile(["가나정"])
    conflicts = risk.analyze(p, ds)
    assert not any(c.flag_type == FlagType.USJNT_TABOO for c in conflicts)


def test_efficacy_duplicate_grouped_once():
    """가나정 + 바사정 = 효능군중복(X-100) 1건."""
    ds = MockDataSource()
    p = _profile(["가나정", "바사정"])
    conflicts = risk.analyze(p, ds)
    dup = [c for c in conflicts if c.flag_type == FlagType.EFCY_DPLCT]
    assert len(dup) == 1
    assert set(dup[0].drugs) == {"가나정", "바사정"}


def test_elderly_caution_only_for_elderly():
    ds = MockDataSource()
    old = risk.analyze(_profile(["마바정"], age=72), ds)
    young = risk.analyze(_profile(["마바정"], age=40, pid="t2"), ds)
    assert any(c.flag_type == FlagType.ODSN_ATENT for c in old)
    assert not any(c.flag_type == FlagType.ODSN_ATENT for c in young)


def test_age_taboo_not_triggered_for_elderly():
    """사아시럽은 만 12세 미만 금기 -> 72세에겐 안 걸려야 한다."""
    ds = MockDataSource()
    conflicts = risk.analyze(_profile(["사아시럽"], age=72), ds)
    assert not any(c.flag_type == FlagType.AGE_TABOO for c in conflicts)


def test_severity_sorted_high_first():
    ds = MockDataSource()
    conflicts = risk.analyze(_profile(["가나정", "다라캡슐", "바사정", "마바정"]), ds)
    severities = [c.severity for c in conflicts]
    assert severities == sorted(severities, key=lambda s: {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}[s])


def test_eval_node_passes_on_clean_output():
    ds = MockDataSource()
    p = _profile(["가나정", "다라캡슐", "마바정"])
    state: PatientState = {"profile": p}
    state.update(nodes.data_node(state, ds))
    state.update(nodes.risk_node(state))
    report = nodes.eval_node(state)["eval_report"]
    assert report["all_cited"] is True
    assert report["hallucinated_drugs"] == []
    assert report["passed"] is True
