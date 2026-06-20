"""
PgDataSource — 성빈 yaksok_db(Cloud SQL PostgreSQL) 실데이터 어댑터.

근일 파이프라인(agents/risk.py)은 DataSource 인터페이스(resolve_drug/dur_records)만 의존하므로,
이 파일을 새로 붙이면 기존 코드(domain/agents/api) 수정 0으로 Mock→실DB 전환이 된다.
(assemble.py 주석 "성빈의 PgDataSource가 붙어도 이 파일은 바뀌지 않는다"의 그 PgDataSource.)

실제 스키마(yakson.*) → 정규화 모델(domain.models) 매핑:
  resolve_drug : drug_item_mfds(item_seq, item_name, company_name)
  dur_records  : 아래 3계열을 item_seq→product_code(drug_product) 경유로 수집
    - 병용금기   product_interaction_rule (product_code_a/b)         → USJNT_TABOO
    - 안전규칙   product_safety_rule.rule_type(enum)                 → 노인/임부/연령/용량/기간
    - 효능군중복 efficacy_group_member + efficacy_group              → EFCY_DPLCT

읽기 전용 계정(spacegiyou_readonly)으로만 조회한다. 어떤 쓰기도 하지 않는다.
"""
from __future__ import annotations

import re

from domain.models import Drug, DurRecord, FlagType, Source

# product_safety_rule / ingredient_safety_rule 의 rule_type(enum) → 로컬 FlagType
_RULE_TYPE_MAP: dict[str, FlagType] = {
    "ELDERLY_CAUTION": FlagType.ODSN_ATENT,
    "ELDERLY_NSAID_CAUTION": FlagType.ODSN_ATENT,
    "AGE_CONTRAINDICATION": FlagType.AGE_TABOO,
    "PREGNANCY_CONTRAINDICATION": FlagType.PWNM_TABOO,
    "DOSAGE_CAUTION": FlagType.CPCTY_ATENT,
    "DURATION_CAUTION": FlagType.PD_ATENT,
    "DUPLICATE_EFFICACY": FlagType.EFCY_DPLCT,
    # LACTATION_CAUTION(수유주의)은 로컬 FlagType에 없음 → 스킵
}

_PROVIDER = "식품의약품안전처 DUR(의약품안전사용서비스)"


def _detect_pim(text: str) -> str | None:
    """노인주의 사유 텍스트에서 고위험 PIM 카테고리 추정(로컬 HIGH_RISK_PIM 값으로 정규화)."""
    t = (text or "").lower()
    if "벤조" in (text or "") and ("다이아제핀" in (text or "") or "디아제핀" in (text or "")):
        return "벤조디아제핀계"
    if "z-drug" in t or "zolpidem" in t or "졸피뎀" in (text or "") or "조피클론" in (text or ""):
        return "Z-drug"
    if "항히스타민" in (text or "") and ("1세대" in (text or "") or "first" in t):
        return "1세대 항히스타민"
    return None


_AGE_NUM = re.compile(r"(\d+)")


class PgDataSource:
    """yaksok_db 실데이터 DataSource. psycopg 연결을 주입받아 읽기 전용 조회."""

    def __init__(self, conn) -> None:
        self.conn = conn

    # ---- 약 해석: 이름/품목기준코드 → Drug ----
    def resolve_drug(self, name_or_seq: str) -> Drug | None:
        key = (name_or_seq or "").strip()
        if not key:
            return None
        with self.conn.cursor() as cur:
            if key.isdigit():
                cur.execute(
                    "SELECT item_seq,item_name,company_name FROM yakson.drug_item_mfds "
                    "WHERE item_seq=%s LIMIT 1",
                    (key,),
                )
                row = cur.fetchone()
                if row:
                    return Drug(item_seq=row[0], name=row[1], entp_name=row[2])
            # 이름 정확 일치 우선
            cur.execute(
                "SELECT item_seq,item_name,company_name FROM yakson.drug_item_mfds "
                "WHERE item_name=%s LIMIT 1",
                (key,),
            )
            row = cur.fetchone()
            if row:
                return Drug(item_seq=row[0], name=row[1], entp_name=row[2])
            # 부분 일치(가장 짧은 이름 = 가장 일반적인 제형 우선)
            cur.execute(
                "SELECT item_seq,item_name,company_name FROM yakson.drug_item_mfds "
                "WHERE item_name ILIKE %s ORDER BY length(item_name) LIMIT 1",
                (f"%{key}%",),
            )
            row = cur.fetchone()
            if row:
                return Drug(item_seq=row[0], name=row[1], entp_name=row[2])
        return None

    def _product_codes(self, item_seq: str) -> list[str]:
        with self.conn.cursor() as cur:
            cur.execute(
                "SELECT product_code FROM yakson.drug_product WHERE item_seq=%s",
                (item_seq,),
            )
            return [r[0] for r in cur.fetchall()]

    # ---- 해당 약의 모든 DUR 플래그 ----
    def dur_records(self, item_seq: str) -> list[DurRecord]:
        pcs = self._product_codes(item_seq)
        if not pcs:
            return []
        out: list[DurRecord] = []
        with self.conn.cursor() as cur:
            # 1) 병용금기 (product_interaction_rule) — 상대 약을 item_seq 로 환원
            cur.execute(
                """
                SELECT DISTINCT pb.item_seq, r.contraindication_reason, r.notice_date,
                       r.product_interaction_rule_id
                FROM yakson.product_interaction_rule r
                JOIN yakson.drug_product pb ON pb.product_code = r.product_code_b
                WHERE r.product_code_a = ANY(%s)
                LIMIT 2000
                """,
                (pcs,),
            )
            seen_rel: set[str] = set()
            for rel_seq, reason, ndate, rid in cur.fetchall():
                if rel_seq == item_seq or rel_seq in seen_rel:
                    continue
                seen_rel.add(rel_seq)
                out.append(DurRecord(
                    flag_type=FlagType.USJNT_TABOO,
                    subject_item_seq=item_seq,
                    prohibit_content=reason or "",
                    related_item_seq=rel_seq,
                    source=Source(provider=_PROVIDER, operation="product_interaction_rule",
                                  notification_date=str(ndate) if ndate else None,
                                  raw_ref=f"product_interaction_rule_id={rid}"),
                ))

            # 2) 안전규칙 (product_safety_rule) — 노인/임부/연령/용량/기간
            cur.execute(
                """
                SELECT rule_type::text, COALESCE(detail_info, remark, ''),
                       age_value, age_unit, age_condition, notice_date, product_safety_rule_id
                FROM yakson.product_safety_rule
                WHERE product_code = ANY(%s)
                """,
                (pcs,),
            )
            seen_safety: set[tuple] = set()
            for rtype, reason, age_value, age_unit, age_cond, ndate, sid in cur.fetchall():
                ft = _RULE_TYPE_MAP.get(rtype)
                if ft is None:
                    continue
                dedup_key = (rtype, reason[:40])
                if dedup_key in seen_safety:
                    continue
                seen_safety.add(dedup_key)
                rec = DurRecord(
                    flag_type=ft,
                    subject_item_seq=item_seq,
                    prohibit_content=reason or "",
                    source=Source(provider=_PROVIDER, operation=f"product_safety_rule:{rtype}",
                                  notification_date=str(ndate) if ndate else None,
                                  raw_ref=f"product_safety_rule_id={sid}"),
                )
                if ft == FlagType.ODSN_ATENT:
                    rec.pim_category = _detect_pim(reason)
                if ft == FlagType.AGE_TABOO and age_value is not None:
                    yrs = int(age_value)
                    # 'YEAR'/'세' 단위 가정. 조건에 따라 범위 추정(보수적).
                    if age_cond and ("UNDER" in str(age_cond).upper() or "미만" in str(age_cond) or "이하" in str(age_cond)):
                        rec.age_min, rec.age_max = 0, yrs
                    else:
                        rec.age_min, rec.age_max = yrs, 200
                out.append(rec)

            # 3) 효능군중복 (efficacy_group_member → group)
            cur.execute(
                """
                SELECT DISTINCT m.efficacy_group_id, g.efficacy_group_name
                FROM yakson.efficacy_group_member m
                JOIN yakson.efficacy_group g ON g.efficacy_group_id = m.efficacy_group_id
                WHERE m.product_code = ANY(%s)
                """,
                (pcs,),
            )
            for gid, gname in cur.fetchall():
                out.append(DurRecord(
                    flag_type=FlagType.EFCY_DPLCT,
                    subject_item_seq=item_seq,
                    prohibit_content="",
                    class_code=str(gid),
                    class_name=gname,
                    source=Source(provider=_PROVIDER, operation="efficacy_group_member",
                                  raw_ref=f"efficacy_group_id={gid}"),
                ))
        return out
