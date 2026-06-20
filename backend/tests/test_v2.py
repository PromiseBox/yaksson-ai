"""
v2 핵심 기능 회귀 테스트 — PIM/handoff/delta/whatif.
기존 test_risk.py 7개 테스트는 별도 유지.
"""
from __future__ import annotations

import pytest
from agents import risk
from agents.handoff import build_intervention_note
from agents.scenarios import compute_delta, simulate_whatif
from domain.models import FlagType, PatientProfile, Severity
from tools.datasource import MockDataSource
from tools.mock_data import find_drug_by_name


def _profile(names: list[str], age: int = 76, pid: str = "t") -> PatientProfile:
    p = PatientProfile(profile_id=pid, alias="아버지", age=age)
    for n in names:
        d = find_drug_by_name(n)
        assert d is not None, f"골든 카탈로그에 {n} 없음"
        p.drugs.append(d)
    return p


def test_high_risk_pim_is_high():
    """고령 프로필 + 벤조원정 → severity 상 & tags에 '치매·낙상 위험'."""
    ds = MockDataSource()
    conflicts = risk.analyze(_profile(["벤조원정"], age=76), ds)
    pim = [c for c in conflicts if c.flag_type == FlagType.ODSN_ATENT]
    assert len(pim) == 1
    assert pim[0].severity == Severity.HIGH
    assert "치매·낙상 위험" in pim[0].tags


def test_pim_not_high_for_non_elderly():
    """같은 벤조원정, 40세 → 노인주의 conflict 없음."""
    ds = MockDataSource()
    conflicts = risk.analyze(_profile(["벤조원정"], age=40, pid="t2"), ds)
    assert not any(c.flag_type == FlagType.ODSN_ATENT for c in conflicts)


def test_intervention_note_has_sources_and_routing():
    """중재의견서에 각 conflict 유형 문자열 + '식약처' + '약사' 포함."""
    ds = MockDataSource()
    p = _profile(["가나정", "다라캡슐", "벤조원정"])
    conflicts = risk.analyze(p, ds)
    note = build_intervention_note(p, conflicts)
    assert "식약처" in note
    assert "약사" in note
    for c in conflicts:
        assert c.flag_type.value in note


def test_whatif_introduces_taboo():
    """base [가나정] → add 다라캡슐 → newly_introduced에 병용금기 존재, before엔 없음."""
    ds = MockDataSource()
    p = _profile(["가나정"])
    r = simulate_whatif(p, ds, add_names=["다라캡슐"])
    assert not any(c.flag_type == FlagType.USJNT_TABOO for c in r["before"])
    taboo = [c for c in r["newly_introduced"] if c.flag_type == FlagType.USJNT_TABOO]
    assert len(taboo) >= 1


def test_delta_returns_new_only():
    """prev [가나정, 마바정], curr +다라캡슐 → new_conflicts에 병용금기 포함, 기존 노인주의는 제외."""
    ds = MockDataSource()
    prev = _profile(["가나정", "마바정"], pid="dp")
    curr = _profile(["가나정", "마바정", "다라캡슐"], pid="dp")
    delta = compute_delta(prev, curr, ds)
    # 새로 생긴 위험에 병용금기 있어야
    new_types = {c.flag_type for c in delta["new_conflicts"]}
    assert FlagType.USJNT_TABOO in new_types
    # 마바정 노인주의는 이미 prev에도 있었으므로 new_conflicts에 없어야
    prev_types = {c.flag_type for c in risk.analyze(prev, ds)}
    pim_was_in_prev = FlagType.ODSN_ATENT in prev_types
    if pim_was_in_prev:
        pim_in_new = [c for c in delta["new_conflicts"] if c.flag_type == FlagType.ODSN_ATENT
                      and "마바정" in c.drugs]
        assert len(pim_in_new) == 0


def test_all_conflicts_have_source():
    """임의 다약제 프로필의 모든 conflict.source.provider 비어있지 않음."""
    ds = MockDataSource()
    p = _profile(["가나정", "다라캡슐", "마바정", "바사정", "벤조원정"])
    conflicts = risk.analyze(p, ds)
    assert len(conflicts) > 0
    for c in conflicts:
        assert c.source and c.source.provider, f"출처 없는 conflict: {c.headline()}"
