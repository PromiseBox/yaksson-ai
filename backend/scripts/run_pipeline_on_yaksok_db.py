"""
근일 파이프라인(랭그래프 위험판정 + 리포트 아웃풋 포맷)을 성빈 yaksok_db 실데이터로 검증.

흐름(기존 코드 무수정): PgDataSource(실DB) → risk.analyze(실제 DUR) → build_report(리포트 포맷)
  = Mock 대신 실데이터를 '붙여서' 동일 파이프라인이 도는지 확인.

실행(프록시 55432 + 비번 env):
  YAKSOK_DB_PASSWORD='***' .venv/bin/python scripts/run_pipeline_on_yaksok_db.py
"""
from __future__ import annotations

import os
import sys

import psycopg

from agents import risk
from agents.assemble import build_report
from domain.models import PatientProfile, Severity
from tools.pg_datasource import PgDataSource


def make_profile(pg: PgDataSource, label: str, names: list[str], age: int) -> PatientProfile:
    p = PatientProfile(profile_id=f"yaksokdb-{label}", alias="아버지", age=age)
    print(f"\n[{label}] 입력 약(이름→실DB 해석): age={age}")
    for n in names:
        d = pg.resolve_drug(n)
        if not d:
            print(f"   ⚠️  '{n}' 해석 실패")
            continue
        p.drugs.append(d)
        nrec = len(pg.dur_records(d.item_seq))
        print(f"   ✓ {d.name} (item_seq={d.item_seq}) — DUR레코드 {nrec}건")
    return p


def show_report(p: PatientProfile, pg: PgDataSource) -> None:
    conflicts = risk.analyze(p, pg)
    state = {
        "profile": p,
        "conflicts": conflicts,
        "needs_pharmacist": any(c.severity == Severity.HIGH for c in conflicts),
    }
    rep = build_report(state)  # ← 근일 코드: 리포트 아웃풋 포맷 조립 + audit
    print(f"   → counts={rep.counts}  needs_pharmacist={rep.needs_pharmacist}  items={len(rep.items)}")
    for it in rep.items:
        src = it.source.operation or it.source.provider
        print(f"      [{it.grade}] {it.flag_type.value}: {' + '.join(it.drugs)}")
        print(f"          사유: {it.reason[:70]}")
        print(f"          출처: {src}  태그={it.tags}")
    audit = rep.eval_report.get("report_audit", {})
    print(f"   → audit passed={audit.get('passed')} source_rate={audit.get('source_rate')} "
          f"hallucination_free={audit.get('hallucination_free')}")
    print(f"   → overall: {rep.overall_message[:90]}")


def main() -> int:
    pw = os.getenv("YAKSOK_DB_PASSWORD", "")
    if not pw:
        print("YAKSOK_DB_PASSWORD 필요", file=sys.stderr)
        return 2
    conn = psycopg.connect(
        host="127.0.0.1", port=55432, dbname="yakson",
        user=os.getenv("YAKSOK_DB_USER", "spacegiyou_readonly"),
        password=pw, autocommit=True, connect_timeout=10,
    )
    pg = PgDataSource(conn)

    print("=" * 70)
    print("근일 파이프라인 × 성빈 yaksok_db 실데이터 검증")
    print("=" * 70)

    # 케이스 A — 병용금기(실제쌍): 중외5-에프유주 ↔ 테고캡슐20
    pA = make_profile(pg, "병용금기", ["중외5-에프유주(플루오로우라실)", "테고캡슐20"], age=68)
    show_report(pA, pg)

    # 케이스 B — 노인주의 PIM(실제): 빅손정(벤조다이아제핀), 고령
    pB = make_profile(pg, "노인주의PIM", ["빅손정1밀리그람(에틸로플라제페이트)"], age=76)
    show_report(pB, pg)

    conn.close()
    print("\n[완료] 실DB 데이터로 근일 파이프라인 end-to-end 동작 확인.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
