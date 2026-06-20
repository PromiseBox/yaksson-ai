"""
골든/Mock 데이터 — 오프라인 개발·테스트·데모 안정성용.

주의: 아래 약품명/금기관계는 *로직 검증을 위한 가상 예시*다.
실제 서비스/발표 데모에서는 tools/mfds_dur_client.py 로 식약처 실데이터를 받아
DurRecord 로 변환해 교체한다. (역할 B 담당)
가상 데이터이므로 어떤 실제 의학적 판단의 근거로도 사용하지 말 것.
"""
from __future__ import annotations

from domain.models import Drug, DurRecord, FlagType, Source

# --- 가상 약품 카탈로그 (정규화된 Drug) ---
DRUG_CATALOG: dict[str, Drug] = {
    "G001": Drug(item_seq="G001", name="가나정", entp_name="가나제약",
                 ingredient_codes=["ING-A"], ingredient_names=["성분-알파"]),
    "D001": Drug(item_seq="D001", name="다라캡슐", entp_name="다라파마",
                 ingredient_codes=["ING-B"], ingredient_names=["성분-베타"]),
    "M001": Drug(item_seq="M001", name="마바정", entp_name="마바약품",
                 ingredient_codes=["ING-C"], ingredient_names=["성분-감마"]),
    "B001": Drug(item_seq="B001", name="바사정", entp_name="바사제약",
                 ingredient_codes=["ING-D"], ingredient_names=["성분-델타"]),
    "S001": Drug(item_seq="S001", name="사아시럽", entp_name="사아헬스",
                 ingredient_codes=["ING-E"], ingredient_names=["성분-엡실론"]),
    "N001": Drug(item_seq="N001", name="벤조원정", entp_name="벤조파마",
                 ingredient_codes=["ING-J"], ingredient_names=["성분-젯"]),
    "Z001": Drug(item_seq="Z001", name="자임정", entp_name="자임약품",
                 ingredient_codes=["ING-Z"], ingredient_names=["성분-제트"]),
    "H001": Drug(item_seq="H001", name="하니정", entp_name="하니제약",
                 ingredient_codes=["ING-H"], ingredient_names=["성분-에이치"]),
}

# --- 가상 DUR 플래그 (정규화된 DurRecord) ---
# 약 item_seq -> 그 약에 걸린 DUR 레코드 목록
_DUR_DB: dict[str, list[DurRecord]] = {
    "G001": [
        # 병용금기: 가나정 <-> 다라캡슐
        DurRecord(
            flag_type=FlagType.USJNT_TABOO,
            subject_item_seq="G001",
            related_item_seq="D001",
            prohibit_content="해당 성분과 병용 시 상호작용으로 이상반응 위험 증가(가상 예시).",
            source=Source(operation="getUsjntTabooInfoList03", notification_date="2025-01-10"),
        ),
        # 효능군중복: 가나정 & 바사정 (같은 분류군 X-100)
        DurRecord(
            flag_type=FlagType.EFCY_DPLCT,
            subject_item_seq="G001",
            class_code="X-100",
            class_name="가상-혈압강하군",
            prohibit_content="동일 효능군 중복 복용 주의(가상 예시).",
            source=Source(operation="getEfcyDplctInfoList03", notification_date="2024-11-05"),
        ),
    ],
    "D001": [
        DurRecord(
            flag_type=FlagType.USJNT_TABOO,
            subject_item_seq="D001",
            related_item_seq="G001",
            prohibit_content="해당 성분과 병용 시 상호작용으로 이상반응 위험 증가(가상 예시).",
            source=Source(operation="getUsjntTabooInfoList03", notification_date="2025-01-10"),
        ),
    ],
    "M001": [
        # 노인주의
        DurRecord(
            flag_type=FlagType.ODSN_ATENT,
            subject_item_seq="M001",
            prohibit_content="65세 이상 고령자에서 낙상·어지럼 위험 증가, 저용량부터 신중 투여(가상 예시).",
            source=Source(operation="getOdsnAtentInfoList03", notification_date="2024-09-01"),
        ),
    ],
    "B001": [
        DurRecord(
            flag_type=FlagType.EFCY_DPLCT,
            subject_item_seq="B001",
            class_code="X-100",
            class_name="가상-혈압강하군",
            prohibit_content="동일 효능군 중복 복용 주의(가상 예시).",
            source=Source(operation="getEfcyDplctInfoList03", notification_date="2024-11-05"),
        ),
    ],
    "S001": [
        # 특정연령금기 (만 12세 미만) — 고령 환자에겐 안 걸리는 케이스 검증용
        DurRecord(
            flag_type=FlagType.AGE_TABOO,
            subject_item_seq="S001",
            age_max=12,
            prohibit_content="만 12세 미만 소아 투여 금기(가상 예시).",
            source=Source(operation="getSpcifyAgrdeTabooInfoList03", notification_date="2023-06-01"),
        ),
    ],
    "N001": [DurRecord(flag_type=FlagType.ODSN_ATENT, subject_item_seq="N001",
        pim_category="벤조디아제핀계",
        prohibit_content="장기작용 벤조디아제핀계는 고령자에서 치매·낙상 위험을 높일 수 있음(가상 예시).",
        source=Source(operation="getOdsnAtentInfoList", notification_date="2024-09-01"))],
    "Z001": [DurRecord(flag_type=FlagType.ODSN_ATENT, subject_item_seq="Z001",
        pim_category="Z-drug",
        prohibit_content="졸피뎀 등 수면제는 고령자에서 낙상·인지저하 위험(가상 예시).",
        source=Source(operation="getOdsnAtentInfoList", notification_date="2024-09-01"))],
    "H001": [DurRecord(flag_type=FlagType.ODSN_ATENT, subject_item_seq="H001",
        pim_category="1세대 항히스타민",
        prohibit_content="1세대 항히스타민은 진정·섬망·낙상 위험(가상 예시).",
        source=Source(operation="getOdsnAtentInfoList", notification_date="2024-09-01"))],
}


def get_drug(item_seq: str) -> Drug | None:
    return DRUG_CATALOG.get(item_seq)


def find_drug_by_name(name: str) -> Drug | None:
    for d in DRUG_CATALOG.values():
        if d.name == name:
            return d
    return None


def get_dur_records(item_seq: str) -> list[DurRecord]:
    return list(_DUR_DB.get(item_seq, []))
