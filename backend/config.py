"""
설정 로더. .env 또는 환경변수에서 읽는다.

DATA_SOURCE=mock  -> 골든 데이터 (기본, 키 불필요)
DATA_SOURCE=mfds  -> 식약처 실 API (MFDS_SERVICE_KEY 필요)
DATA_SOURCE=pg    -> yaksok_db (Cloud SQL, cloud-sql-proxy 경유; YAKSOK_DB_* 필요)
LLM_PROVIDER      -> comm 단계 자연어 다듬기에 사용할 LLM (기본 template; api 키 있으면 claude)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass
class Settings:
    data_source: str = os.getenv("DATA_SOURCE", "mock")
    mfds_service_key: str = os.getenv("MFDS_SERVICE_KEY", "")
    llm_provider: str = os.getenv("LLM_PROVIDER", "template")  # template|gpt-5.5|claude|gemini
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    # v3: GPT-5.5 설명 생성(근일). 서버 전용 — 프론트 노출 금지(Secret Manager로 주입).
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-5.5")
    # DATA_SOURCE=pg: yaksok_db(Cloud SQL via cloud-sql-proxy). 비번은 env/Secret Manager로 주입(코드·리포 미포함).
    db_host: str = os.getenv("YAKSOK_DB_HOST", "127.0.0.1")
    db_port: int = int(os.getenv("YAKSOK_DB_PORT", "55432"))
    db_name: str = os.getenv("YAKSOK_DB_NAME", "yakson")
    db_user: str = os.getenv("YAKSOK_DB_USER", "spacegiyou_readonly")
    db_password: str = os.getenv("YAKSOK_DB_PASSWORD", "")


settings = Settings()
