import os
import re
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Final

import psycopg
import pytest
from psycopg import sql

from litellm.proxy.db.daily_spend_bulk_upsert import (
    DAILY_SPEND_TABLES,
    DailySpendTable,
    build_bulk_upsert,
    merge_by_conflict_key,
)

_MIGRATION: Final = (
    Path(__file__).resolve().parents[3]
    / "litellm-proxy-extras/litellm_proxy_extras/migrations/20261027000000_preserve_daily_spend_model_group/migration.sql"
)
_INDEX_NAMES: Final = (
    "LiteLLM_DailyUserSpend_user_id_date_api_key_model_custom_ll_key",
    "LiteLLM_DailyTeamSpend_team_id_date_api_key_model_custom_ll_key",
    "LiteLLM_DailyOrganizationSpend_organization_id_date_api_key_key",
    "LiteLLM_DailyEndUserSpend_end_user_id_date_api_key_model_cu_key",
    "LiteLLM_DailyAgentSpend_agent_id_date_api_key_model_custom__key",
    "LiteLLM_DailyTagSpend_tag_date_api_key_model_custom_llm_pro_key",
)
_COUNTERS: Final = (
    "prompt_tokens",
    "completion_tokens",
    "api_requests",
    "successful_requests",
    "failed_requests",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "compression_saved_tokens",
    "total_response_time_ms",
    "timed_requests",
)
_COSTS: Final = (
    "spend",
    "compression_savings_spend",
    "prompt_caching_savings_spend",
    "gateway_injected_caching_savings_spend",
    "autorouter_savings_spend",
)


@pytest.fixture(params=("official", "custom", "both"))
def rollup_database(request) -> Iterator[tuple[psycopg.Connection, str]]:
    schema = f"upgrade_rollup_{uuid.uuid4().hex}"
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
        try:
            connection.execute(sql.SQL("SET search_path TO {}").format(sql.Identifier(schema)))
            for table, index in zip(DAILY_SPEND_TABLES.values(), _INDEX_NAMES, strict=True):
                text_fields = (
                    table.entity_id_column,
                    "date",
                    "api_key",
                    "model",
                    "model_group",
                    "custom_llm_provider",
                    "mcp_namespaced_tool_name",
                    "endpoint",
                    "request_id",
                )
                fields = (
                    '"id" TEXT PRIMARY KEY',
                    *(f'"{field}" TEXT' for field in text_fields),
                    *(f'"{field}" BIGINT NOT NULL DEFAULT 0' for field in _COUNTERS),
                    *(f'"{field}" DOUBLE PRECISION NOT NULL DEFAULT 0' for field in _COSTS),
                    '"updated_at" TIMESTAMP NOT NULL DEFAULT NOW()',
                )
                connection.execute(
                    sql.SQL("CREATE TABLE {} ({})").format(sql.Identifier(table.name), sql.SQL(", ".join(fields)))
                )
                key = (
                    table.entity_id_column,
                    "date",
                    "api_key",
                    "model",
                    "custom_llm_provider",
                    "mcp_namespaced_tool_name",
                    "endpoint",
                )
                if request.param in ("official", "both"):
                    connection.execute(
                        sql.SQL("CREATE UNIQUE INDEX {} ON {} ({})").format(
                            sql.Identifier(index),
                            sql.Identifier(table.name),
                            sql.SQL(", ").join(map(sql.Identifier, key)),
                        )
                    )
                if request.param in ("custom", "both"):
                    custom_key = (*key[:4], "model_group", *key[4:])
                    connection.execute(
                        sql.SQL("CREATE UNIQUE INDEX {} ON {} ({})").format(
                            sql.Identifier(index if request.param == "custom" else "custom_" + index[:50]),
                            sql.Identifier(table.name),
                            sql.SQL(", ").join(map(sql.Identifier, custom_key)),
                        )
                    )
            yield connection, schema
        finally:
            connection.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def _write(connection: psycopg.Connection, table: DailySpendTable, public_name: str | None) -> None:
    transaction = {
        table.entity_id_column: "entity",
        "date": "2026-10-01",
        "api_key": "hash",
        "model": "same-backend",
        "model_group": public_name,
        "custom_llm_provider": "openai",
        "mcp_namespaced_tool_name": "",
        "endpoint": "/chat/completions",
        "spend": 1.25,
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "api_requests": 1,
        "successful_requests": 1,
        "cache_read_input_tokens": 7,
        "cache_creation_input_tokens": 2,
    }
    statement, parameters = build_bulk_upsert(table, merge_by_conflict_key(table, (transaction,)))
    connection.execute(re.sub(r"\$\d+", "%s", statement), parameters)


@pytest.mark.parametrize("table", tuple(DAILY_SPEND_TABLES.values()), ids=tuple(DAILY_SPEND_TABLES))
def test_migration_preserves_history_and_keeps_concurrent_public_model_spend_separate(rollup_database, table):
    connection, schema = rollup_database
    connection.execute(
        sql.SQL("INSERT INTO {} (id, {}, date, api_key, model, model_group) VALUES (%s, %s, %s, %s, %s, NULL)").format(
            sql.Identifier(table.name), sql.Identifier(table.entity_id_column)
        ),
        ("historical", "entity", "2026-10-01", "hash", "same-backend"),
    )
    history_before = connection.execute(
        sql.SQL("SELECT * FROM {} WHERE id = 'historical'").format(sql.Identifier(table.name))
    ).fetchone()
    migration = _MIGRATION.read_text()
    connection.execute(migration)
    indexes_before = connection.execute(
        "SELECT indexrelid FROM pg_index WHERE indrelid = %s::regclass ORDER BY indexrelid", (f'"{table.name}"',)
    ).fetchall()
    connection.execute(migration)
    assert (
        connection.execute(
            "SELECT indexrelid FROM pg_index WHERE indrelid = %s::regclass ORDER BY indexrelid", (f'"{table.name}"',)
        ).fetchall()
        == indexes_before
    )
    assert (
        connection.execute(
            sql.SQL("SELECT * FROM {} WHERE id = 'historical'").format(sql.Identifier(table.name))
        ).fetchone()
        == history_before
    )

    def writer(_: int) -> None:
        with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True, options=f"-c search_path={schema}") as worker:
            for public_name in ("public-a", "public-b", None, ""):
                _write(worker, table, public_name)

    with ThreadPoolExecutor(max_workers=4) as pool:
        tuple(pool.map(writer, range(8)))
    rows = connection.execute(
        sql.SQL(
            "SELECT model_group, spend, prompt_tokens, completion_tokens, api_requests, cache_read_input_tokens, cache_creation_input_tokens FROM {} WHERE id <> %s ORDER BY model_group"
        ).format(sql.Identifier(table.name)),
        ("historical",),
    ).fetchall()
    assert rows == [
        ("", 20.0, 160, 80, 16, 112, 32),
        ("public-a", 10.0, 80, 40, 8, 56, 16),
        ("public-b", 10.0, 80, 40, 8, 56, 16),
    ]
