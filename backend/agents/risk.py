"""
위험 판정 엔진 (Interaction Risk) — 제품 가치의 핵심.

입력: 환자 프로필(약 목록 + 나이/임신여부) + DataSource
출력: Conflict 목록 (각 항목은 식약처 근거 + 출처 + 심각도 + 전문가 확인 권고 포함)

원칙:
- 우리는 진단/처방하지 않는다. 식약처가 '등재'한 금기/주의를 환자의 실제 약 조합에 대입해
  '해당됨'을 알리고, 최종 판단은 약사·의사로 라우팅한다.
- 모든 Conflict 에는 출처(Source)가 반드시 붙는다 (Evaluation Agent가 강제).
"""
from __future__ import annotations

from collections import defaultdict

from domain.models import (
    Conflict,
    Drug,
    DurRecord,
    FlagType,
    PatientProfile,
    Severity,
    Source,
)
from tools.datasource import DataSource

# 유형별 기본 심각도
_SEVERITY = {
    FlagType.USJNT_TABOO: Severity.HIGH,
    FlagType.PWNM_TABOO: Severity.HIGH,
    FlagType.AGE_TABOO: Severity.HIGH,
    FlagType.EFCY_DPLCT: Severity.MEDIUM,
    FlagType.ODSN_ATENT: Severity.MEDIUM,
    FlagType.CPCTY_ATENT: Severity.LOW,
    FlagType.PD_ATENT: Severity.LOW,
}

_REC_EXPERT = "최종 판단이 아닙니다. 처방받은 병원·약국 또는 가까운 약사에게 이 조합을 확인하세요."

HIGH_RISK_PIM = {"벤조디아제핀계", "Z-drug", "1세대 항히스타민"}


def collect_records(profile: PatientProfile, ds: DataSource) -> dict[str, list[DurRecord]]:
    """프로필의 각 약에 대한 DUR 레코드를 수집."""
    out: dict[str, list[DurRecord]] = {}
    for drug in profile.drugs:
        out[drug.item_seq] = ds.dur_records(drug.item_seq)
    return out


def detect_conflicts(
    profile: PatientProfile,
    records_by_drug: dict[str, list[DurRecord]],
) -> list[Conflict]:
    drugs_by_seq: dict[str, Drug] = {d.item_seq: d for d in profile.drugs}
    present_seqs = set(drugs_by_seq.keys())
    conflicts: list[Conflict] = []
    seen_pairs: set[frozenset[str]] = set()  # 병용금기 양방향 중복 제거

    # 효능군중복 집계용: class_code -> {item_seq -> record}
    class_buckets: dict[str, dict[str, DurRecord]] = defaultdict(dict)

    for seq, records in records_by_drug.items():
        subject = drugs_by_seq.get(seq)
        if subject is None:
            continue
        for rec in records:
            ft = rec.flag_type

            if ft == FlagType.USJNT_TABOO:
                rel = rec.related_item_seq
                # 상대 약이 환자의 약 목록에 실제로 있을 때만 '해당'
                if rel and rel in present_seqs and rel != seq:
                    pair = frozenset({seq, rel})
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    conflicts.append(Conflict(
                        flag_type=ft,
                        severity=_SEVERITY[ft],
                        drugs=[subject.name, drugs_by_seq[rel].name],
                        reason=rec.prohibit_content or "식약처 DUR 병용금기로 등재된 조합입니다.",
                        recommendation=_REC_EXPERT,
                        source=rec.source,
                    ))

            elif ft == FlagType.EFCY_DPLCT:
                if rec.class_code:
                    class_buckets[rec.class_code][seq] = rec

            elif ft == FlagType.ODSN_ATENT:
                if profile.is_elderly:
                    cat = rec.pim_category
                    sev = Severity.HIGH if cat in HIGH_RISK_PIM else _SEVERITY[FlagType.ODSN_ATENT]
                    tags = ["치매·낙상 위험"] if cat in HIGH_RISK_PIM else []
                    conflicts.append(Conflict(
                        flag_type=ft,
                        severity=sev,
                        drugs=[subject.name],
                        reason=rec.prohibit_content or "고령자 주의 약물로 등재되어 있습니다.",
                        recommendation=_REC_EXPERT,
                        source=rec.source,
                        tags=tags,
                    ))

            elif ft == FlagType.AGE_TABOO:
                age = profile.age
                if age is not None and _age_in_range(age, rec):
                    conflicts.append(Conflict(
                        flag_type=ft,
                        severity=_SEVERITY[ft],
                        drugs=[subject.name],
                        reason=rec.prohibit_content or "해당 연령 금기 약물입니다.",
                        recommendation=_REC_EXPERT,
                        source=rec.source,
                    ))

            elif ft == FlagType.PWNM_TABOO:
                if profile.is_pregnant:
                    conflicts.append(Conflict(
                        flag_type=ft,
                        severity=_SEVERITY[ft],
                        drugs=[subject.name],
                        reason=rec.prohibit_content or "임부 금기 약물입니다.",
                        recommendation=_REC_EXPERT,
                        source=rec.source,
                    ))

            elif ft in (FlagType.CPCTY_ATENT, FlagType.PD_ATENT):
                conflicts.append(Conflict(
                    flag_type=ft,
                    severity=_SEVERITY[ft],
                    drugs=[subject.name],
                    reason=rec.prohibit_content or f"{ft.value} 항목으로 등재되어 있습니다.",
                    recommendation=_REC_EXPERT,
                    source=rec.source,
                ))

    # 효능군중복: 같은 분류군에 2개 이상 약이 있으면 1건의 Conflict
    for class_code, members in class_buckets.items():
        if len(members) >= 2:
            names = [drugs_by_seq[s].name for s in members]
            any_rec = next(iter(members.values()))
            conflicts.append(Conflict(
                flag_type=FlagType.EFCY_DPLCT,
                severity=_SEVERITY[FlagType.EFCY_DPLCT],
                drugs=names,
                reason=(any_rec.class_name or class_code)
                       + " 동일 효능군 약물을 함께 복용 중입니다(중복).",
                recommendation=_REC_EXPERT,
                source=any_rec.source,
            ))

    # 심각도 높은 순 정렬
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    conflicts.sort(key=lambda c: order[c.severity])
    return conflicts


def _age_in_range(age_years: int, rec: DurRecord) -> bool:
    lo = rec.age_min if rec.age_min is not None else -1
    hi = rec.age_max if rec.age_max is not None else 200
    return lo <= age_years <= hi


def analyze(profile: PatientProfile, ds: DataSource) -> list[Conflict]:
    """편의 진입점."""
    return detect_conflicts(profile, collect_records(profile, ds))
