"""
yaksok_db 직접 접속 테스트 (본인이 비밀번호를 직접 입력).

- cloud-sql-proxy가 127.0.0.1:55432 에 떠 있어야 한다(이미 실행 중이면 그대로).
- 비밀번호는 getpass로 입력 → 화면/쉘 히스토리에 남지 않음.
- 성공: current_database/current_user + 스키마 테이블 수 출력.
- 실패: PostgreSQL이 준 정확한 메시지 출력.

실행:
  .venv/bin/python scripts/try_connect.py
  (계정·포트를 바꾸려면)  YAKSOK_DB_USER=다른계정 YAKSOK_DB_PORT=5432 .venv/bin/python scripts/try_connect.py
"""
from __future__ import annotations

import getpass
import os
import sys

import psycopg

host = os.getenv("YAKSOK_DB_HOST", "127.0.0.1")
port = int(os.getenv("YAKSOK_DB_PORT", "55432"))
dbname = os.getenv("YAKSOK_DB_NAME", "yakson")
default_user = os.getenv("YAKSOK_DB_USER", "spacegiyou_readonly")

print(f"접속 대상: {host}:{port}  db={dbname}")
user = input(f"DB 계정 [{default_user}]: ").strip() or default_user
password = getpass.getpass("DB 비밀번호(입력해도 화면에 안 보임): ")

if not password:
    print("비밀번호가 비어 있습니다.", file=sys.stderr)
    raise SystemExit(2)

try:
    with psycopg.connect(
        host=host, port=port, dbname=dbname, user=user, password=password,
        connect_timeout=10, autocommit=True,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT current_database(), current_user;")
            db, who = cur.fetchone()
            cur.execute(
                """
                SELECT count(*) FROM information_schema.tables
                WHERE table_schema IN ('yakson', 'yakson_raw');
                """
            )
            ntables = cur.fetchone()[0]
    print("\n✅ 접속 성공!")
    print(f"   database = {db}")
    print(f"   user     = {who}")
    print(f"   yakson/yakson_raw 테이블 수 = {ntables}")
    print("\n→ 자격증명 정상입니다. 알려주시면 제가 스키마 확인·PgDataSource 작성으로 바로 진행합니다.")
except psycopg.OperationalError as e:
    msg = str(e).strip().splitlines()[0]
    print(f"\n❌ 접속 실패: {msg}", file=sys.stderr)
    if "password authentication failed" in msg:
        print("   → 비번이 틀렸거나 계정이 아직 없습니다(성빈님 확인 필요).", file=sys.stderr)
    elif "Connection refused" in msg or "could not connect" in msg:
        print("   → cloud-sql-proxy(55432)가 안 떠 있습니다.", file=sys.stderr)
    raise SystemExit(1)
