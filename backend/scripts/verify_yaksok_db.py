"""
yaksok_db 연결 검증 스크립트 (근일 로컬 파일 ↔ 성빈 Cloud SQL '붙여서 확인').

이 스크립트는 어떤 기존 코드도 수정하지 않는다. 오직 읽기 전용으로:
  1) cloud-sql-proxy(127.0.0.1:55432)를 통해 yakson DB에 접속하고
  2) Notion 'yaksok_db 접속 방법'의 확인 SQL을 그대로 실행하며
  3) yakson / yakson_raw 스키마의 실제 테이블·컬럼·행수를 introspection 한다.

접속 정보는 환경변수로 받는다(비밀번호를 코드/리포에 남기지 않기 위함):
  YAKSOK_DB_HOST  (기본 127.0.0.1)
  YAKSOK_DB_PORT  (기본 55432)
  YAKSOK_DB_NAME  (기본 yakson)
  YAKSOK_DB_USER  (기본 spacegiyou_readonly)   ← 근일 readonly 계정
  YAKSOK_DB_PASSWORD                            ← Notion 표기 비밀번호 (런타임 주입)

실행(프록시가 떠 있는 상태에서):
  YAKSOK_DB_PASSWORD='***' .venv/bin/python scripts/verify_yaksok_db.py
"""
from __future__ import annotations

import json
import os
import sys

import psycopg

CONN = dict(
    host=os.getenv("YAKSOK_DB_HOST", "127.0.0.1"),
    port=int(os.getenv("YAKSOK_DB_PORT", "55432")),
    dbname=os.getenv("YAKSOK_DB_NAME", "yakson"),
    user=os.getenv("YAKSOK_DB_USER", "spacegiyou_readonly"),
    password=os.getenv("YAKSOK_DB_PASSWORD", ""),
)


def _line(title: str) -> None:
    print(f"\n{'─' * 4} {title} {'─' * 4}")


def main() -> int:
    if not CONN["password"]:
        print("[중단] YAKSOK_DB_PASSWORD 환경변수가 비어 있습니다.", file=sys.stderr)
        return 2

    masked = {**CONN, "password": "***"}
    print("[접속 시도]", json.dumps(masked, ensure_ascii=False))

    try:
        # 읽기 전용 검증: 트랜잭션을 열지 않도록 autocommit
        with psycopg.connect(**CONN, connect_timeout=10, autocommit=True) as conn:
            with conn.cursor() as cur:
                # 1) Notion 확인 SQL
                _line("SELECT current_database(), current_user")
                cur.execute("SELECT current_database(), current_user;")
                db, who = cur.fetchone()
                print(f"  database = {db}")
                print(f"  user     = {who}")

                # 2) 서버 버전
                cur.execute("SHOW server_version;")
                print(f"  postgres = {cur.fetchone()[0]}")

                # 3) Notion 테이블 확인 SQL
                _line("yakson / yakson_raw 테이블 목록")
                cur.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema IN ('yakson', 'yakson_raw')
                    ORDER BY table_schema, table_name;
                    """
                )
                rows = cur.fetchall()
                if not rows:
                    print("  (테이블 없음 — 스키마 권한 확인 필요)")
                cur_schema = None
                for schema, name in rows:
                    if schema != cur_schema:
                        cur_schema = schema
                        print(f"  [{schema}]")
                    print(f"    - {name}")

                # 4) yakson(정규화) 스키마 각 테이블: 컬럼 + 행수
                _line("yakson 스키마 상세 (컬럼 / 행수)")
                tables = [n for s, n in rows if s == "yakson"]
                for t in tables:
                    cur.execute(
                        """
                        SELECT column_name, data_type
                        FROM information_schema.columns
                        WHERE table_schema = 'yakson' AND table_name = %s
                        ORDER BY ordinal_position;
                        """,
                        (t,),
                    )
                    cols = cur.fetchall()
                    cur.execute(f'SELECT count(*) FROM yakson."{t}";')
                    n = cur.fetchone()[0]
                    print(f"\n  ◆ yakson.{t}  ({n:,} rows)")
                    for cname, ctype in cols:
                        print(f"      {cname:<28} {ctype}")

        print("\n[성공] yaksok_db 연결·조회 검증 완료 (읽기 전용).")
        return 0

    except psycopg.OperationalError as e:
        print(f"\n[연결 실패] {e}", file=sys.stderr)
        print(
            "  → cloud-sql-proxy가 127.0.0.1:55432에 떠 있는지, "
            "gcloud ADC 인증이 됐는지 확인하세요.",
            file=sys.stderr,
        )
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"\n[오류] {type(e).__name__}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
