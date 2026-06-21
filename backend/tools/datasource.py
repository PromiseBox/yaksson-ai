"""
DataSource 추상화.

핵심 로직(risk engine)은 DataSource 인터페이스만 의존한다.
- MockDataSource: 골든 데이터 (오프라인 개발/테스트/안정적 데모)
- MfdsDataSource: 식약처 실 API (tools/mfds_dur_client.py 의 raw 응답을 DurRecord로 정규화)

데모/심사 때는 환경변수로 둘을 스위칭한다 (config.DATA_SOURCE).
"""
from __future__ import annotations

from typing import Protocol

from domain.models import Drug, DurRecord
from tools import mock_data


class DataSource(Protocol):
    def resolve_drug(self, name_or_seq: str) -> Drug | None:
        """약명 또는 품목기준코드를 정규화된 Drug로 해석."""
        ...

    def dur_records(self, item_seq: str) -> list[DurRecord]:
        """해당 약에 걸린 모든 DUR 플래그(병용/효능군중복/노인주의/연령/임부 등)."""
        ...


class MockDataSource:
    """골든 데이터 기반. 네트워크/서비스키 불필요."""

    def resolve_drug(self, name_or_seq: str) -> Drug | None:
        d = mock_data.get_drug(name_or_seq)
        if d:
            return d
        return mock_data.find_drug_by_name(name_or_seq)

    def dur_records(self, item_seq: str) -> list[DurRecord]:
        return mock_data.get_dur_records(item_seq)


class MfdsDataSource:
    """
    식약처 실 API 어댑터.

    역할 B 작업 포인트:
    - tools/mfds_dur_client.MfdsDurClient 로 각 오퍼레이션을 호출하고
    - raw JSON -> domain.models.DurRecord 로 매핑 (필드명은 Swagger에서 최종 확인)
    - resolve_drug: 약명 -> 품목기준코드 매핑 (e약은요/낱알식별 활용)
    아래는 골격이며, 실제 매핑은 client 검증 후 채운다.
    """

    def __init__(self, client) -> None:
        self.client = client

    def resolve_drug(self, name_or_seq: str) -> Drug | None:
        return self.client.resolve_drug(name_or_seq)

    def dur_records(self, item_seq: str) -> list[DurRecord]:
        return self.client.dur_records(item_seq)


_pg_datasource = None  # pg 연결은 한 run 안의 노드들이 공유(매 노드 새 커넥션 방지)


def get_default_datasource() -> DataSource:
    """config 기반 팩토리. 키/연결이 없으면 자동으로 Mock 사용."""
    from config import settings

    if settings.data_source == "mfds" and settings.mfds_service_key:
        from tools.mfds_dur_client import MfdsDurClient
        return MfdsDataSource(MfdsDurClient(settings.mfds_service_key))
    if settings.data_source == "pg" and settings.db_password:
        return _get_pg_datasource()
    return MockDataSource()


def _get_pg_datasource() -> DataSource:
    """yaksok_db(Cloud SQL) PgDataSource. 연결은 1회 생성해 캐시(노드 간 공유)."""
    global _pg_datasource
    if _pg_datasource is None:
        import psycopg

        from config import settings
        from tools.pg_datasource import PgDataSource

        conn = psycopg.connect(
            host=settings.db_host, port=settings.db_port, dbname=settings.db_name,
            user=settings.db_user, password=settings.db_password,
            autocommit=True, connect_timeout=10,
        )
        _pg_datasource = PgDataSource(conn)
    return _pg_datasource
