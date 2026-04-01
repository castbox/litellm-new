#!/usr/bin/env python3
"""Export LiteLLM spend logs for routing backtests.

Example:
    poetry run python scripts/export_spend_logs_for_routing_backtest.py \
        --model-group ai-seek-gemini-flash-lite \
        --start 2026-03-01T00:00:00+08:00 \
        --end 2026-03-08T00:00:00+08:00 \
        --format jsonl \
        --output /tmp/gemini_flash_lite_backtest.jsonl
"""

import argparse
import asyncio
import csv
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Sequence

if TYPE_CHECKING:
    from prisma import Prisma


SELECT_COLUMNS = [
    'request_id',
    'call_type',
    'api_key',
    'spend',
    'total_tokens',
    'prompt_tokens',
    'completion_tokens',
    '"startTime"',
    '"endTime"',
    '"completionStartTime"',
    'model',
    'model_id',
    'model_group',
    'custom_llm_provider',
    'api_base',
    '"user"',
    'metadata',
    'cache_hit',
    'cache_key',
    'request_tags',
    'team_id',
    'organization_id',
    'end_user',
    'requester_ip_address',
    'messages',
    'response',
    'session_id',
    'status',
    'mcp_namespaced_tool_name',
    'agent_id',
    'proxy_server_request',
]

CSV_FIELDS = [
    'request_id',
    'call_type',
    'start_time',
    'end_time',
    'completion_start_time',
    'latency_seconds',
    'ttft_seconds',
    'effective_latency_seconds',
    'model_group',
    'model_id',
    'model',
    'api_base',
    'custom_llm_provider',
    'status',
    'spend',
    'prompt_tokens',
    'completion_tokens',
    'total_tokens',
    'is_stream',
    'selected_reason',
    'selected_deployment_id',
    'cache_hit',
    'cache_key',
    'team_id',
    'organization_id',
    'end_user',
    'requester_ip_address',
    'session_id',
    'mcp_namespaced_tool_name',
    'agent_id',
    'request_tags_json',
    'metadata_json',
    'proxy_server_request_json',
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Export LiteLLM spend logs for routing backtests.'
    )
    parser.add_argument('--output', required=True, help='Output file path (.jsonl or .csv).')
    parser.add_argument('--format', choices=['jsonl', 'csv'], default='jsonl')
    parser.add_argument('--model-group', help='Only export rows for this model_group.')
    parser.add_argument('--deployment-id', action='append', default=[], help='Filter by one or more model_id values.')
    parser.add_argument('--status', action='append', default=[], help='Filter by request status, e.g. success or failure.')
    parser.add_argument('--team-id', help='Optional team_id filter.')
    parser.add_argument('--start', help='Inclusive ISO-8601 start timestamp, e.g. 2026-03-01T00:00:00+08:00.')
    parser.add_argument('--end', help='Exclusive ISO-8601 end timestamp, e.g. 2026-03-08T00:00:00+08:00.')
    parser.add_argument('--limit', type=int, help='Maximum number of rows to export.')
    parser.add_argument('--batch-size', type=int, default=5000, help='Rows per DB batch. Default: 5000.')
    parser.add_argument('--order', choices=['asc', 'desc'], default='asc', help='Sort order by startTime. Default: asc.')
    parser.add_argument('--database-url', help='Optional DATABASE_URL override.')
    return parser.parse_args()


def parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith('Z'):
        normalized = normalized[:-1] + '+00:00'
    if 'T' not in normalized:
        normalized = normalized + 'T00:00:00+00:00'
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def maybe_parse_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if stripped == '':
            return None
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def isoformat_or_none(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def seconds_between(start: Any, end: Any) -> Optional[float]:
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        return None
    return max(0.0, (end - start).total_seconds())


def infer_stream_flag(proxy_server_request: Any, metadata: Any) -> Optional[bool]:
    parsed_request = maybe_parse_json(proxy_server_request)
    if isinstance(parsed_request, dict):
        body = parsed_request.get('body')
        if isinstance(body, dict) and isinstance(body.get('stream'), bool):
            return body['stream']
    parsed_metadata = maybe_parse_json(metadata)
    if isinstance(parsed_metadata, dict):
        for key in ('stream', 'is_stream'):
            if isinstance(parsed_metadata.get(key), bool):
                return parsed_metadata[key]
    return None


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    metadata = maybe_parse_json(row.get('metadata'))
    request_tags = maybe_parse_json(row.get('request_tags'))
    proxy_server_request = maybe_parse_json(row.get('proxy_server_request'))
    response = maybe_parse_json(row.get('response'))
    messages = maybe_parse_json(row.get('messages'))

    start_time = row.get('startTime')
    end_time = row.get('endTime')
    completion_start_time = row.get('completionStartTime')

    latency_seconds = seconds_between(start_time, end_time)
    ttft_seconds = seconds_between(start_time, completion_start_time)
    effective_latency_seconds = ttft_seconds if ttft_seconds is not None else latency_seconds

    selected_reason = None
    selected_deployment_id = None
    slo_pass_set = None
    score_breakdown = None
    if isinstance(metadata, dict):
        selected_reason = metadata.get('_selected_reason')
        selected_deployment_id = metadata.get('_selected_deployment_id')
        slo_pass_set = metadata.get('_slo_pass_set')
        score_breakdown = metadata.get('_score_breakdown')

    return {
        'request_id': row.get('request_id'),
        'call_type': row.get('call_type'),
        'api_key': row.get('api_key'),
        'spend': row.get('spend'),
        'total_tokens': row.get('total_tokens'),
        'prompt_tokens': row.get('prompt_tokens'),
        'completion_tokens': row.get('completion_tokens'),
        'start_time': isoformat_or_none(start_time),
        'end_time': isoformat_or_none(end_time),
        'completion_start_time': isoformat_or_none(completion_start_time),
        'latency_seconds': latency_seconds,
        'ttft_seconds': ttft_seconds,
        'effective_latency_seconds': effective_latency_seconds,
        'model': row.get('model'),
        'model_id': row.get('model_id'),
        'model_group': row.get('model_group'),
        'custom_llm_provider': row.get('custom_llm_provider'),
        'api_base': row.get('api_base'),
        'user': row.get('user'),
        'metadata': metadata,
        'cache_hit': row.get('cache_hit'),
        'cache_key': row.get('cache_key'),
        'request_tags': request_tags,
        'team_id': row.get('team_id'),
        'organization_id': row.get('organization_id'),
        'end_user': row.get('end_user'),
        'requester_ip_address': row.get('requester_ip_address'),
        'messages': messages,
        'response': response,
        'session_id': row.get('session_id'),
        'status': row.get('status'),
        'mcp_namespaced_tool_name': row.get('mcp_namespaced_tool_name'),
        'agent_id': row.get('agent_id'),
        'proxy_server_request': proxy_server_request,
        'is_stream': infer_stream_flag(proxy_server_request, metadata),
        'selected_reason': selected_reason,
        'selected_deployment_id': selected_deployment_id,
        'slo_pass_set': slo_pass_set,
        'score_breakdown': score_breakdown,
    }


def row_to_csv_dict(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        'request_id': row.get('request_id'),
        'call_type': row.get('call_type'),
        'start_time': row.get('start_time'),
        'end_time': row.get('end_time'),
        'completion_start_time': row.get('completion_start_time'),
        'latency_seconds': row.get('latency_seconds'),
        'ttft_seconds': row.get('ttft_seconds'),
        'effective_latency_seconds': row.get('effective_latency_seconds'),
        'model_group': row.get('model_group'),
        'model_id': row.get('model_id'),
        'model': row.get('model'),
        'api_base': row.get('api_base'),
        'custom_llm_provider': row.get('custom_llm_provider'),
        'status': row.get('status'),
        'spend': row.get('spend'),
        'prompt_tokens': row.get('prompt_tokens'),
        'completion_tokens': row.get('completion_tokens'),
        'total_tokens': row.get('total_tokens'),
        'is_stream': row.get('is_stream'),
        'selected_reason': row.get('selected_reason'),
        'selected_deployment_id': row.get('selected_deployment_id'),
        'cache_hit': row.get('cache_hit'),
        'cache_key': row.get('cache_key'),
        'team_id': row.get('team_id'),
        'organization_id': row.get('organization_id'),
        'end_user': row.get('end_user'),
        'requester_ip_address': row.get('requester_ip_address'),
        'session_id': row.get('session_id'),
        'mcp_namespaced_tool_name': row.get('mcp_namespaced_tool_name'),
        'agent_id': row.get('agent_id'),
        'request_tags_json': json.dumps(row.get('request_tags'), ensure_ascii=True, default=str),
        'metadata_json': json.dumps(row.get('metadata'), ensure_ascii=True, default=str),
        'proxy_server_request_json': json.dumps(row.get('proxy_server_request'), ensure_ascii=True, default=str),
    }


class SpendLogExporter:
    def __init__(self, args: argparse.Namespace):
        try:
            from prisma import Prisma
        except ImportError as exc:  # pragma: no cover - import guard
            raise SystemExit(
                "Missing dependency 'prisma'. Install project dependencies first."
            ) from exc

        self.args = args
        self.db = Prisma(http={'timeout': 60000})

    async def run(self) -> int:
        database_url = self.args.database_url or os.getenv('DATABASE_URL')
        if not database_url:
            raise SystemExit(
                'DATABASE_URL is not set. Pass --database-url or export DATABASE_URL first.'
            )

        if self.args.database_url:
            os.environ['DATABASE_URL'] = self.args.database_url

        output_path = Path(self.args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        await self.db.connect()
        try:
            return await self._export(output_path)
        finally:
            await self.db.disconnect()

    async def _export(self, output_path: Path) -> int:
        exported = 0
        offset = 0
        remaining = self.args.limit

        if self.args.format == 'jsonl':
            with output_path.open('w', encoding='utf-8') as handle:
                while True:
                    batch = await self._fetch_batch(offset=offset, remaining=remaining)
                    if not batch:
                        break
                    for raw_row in batch:
                        normalized = normalize_row(raw_row)
                        handle.write(json.dumps(normalized, ensure_ascii=True, default=str) + '\n')
                        exported += 1
                    offset += len(batch)
                    if remaining is not None:
                        remaining -= len(batch)
                        if remaining <= 0:
                            break
        else:
            with output_path.open('w', encoding='utf-8', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
                writer.writeheader()
                while True:
                    batch = await self._fetch_batch(offset=offset, remaining=remaining)
                    if not batch:
                        break
                    for raw_row in batch:
                        writer.writerow(row_to_csv_dict(normalize_row(raw_row)))
                        exported += 1
                    offset += len(batch)
                    if remaining is not None:
                        remaining -= len(batch)
                        if remaining <= 0:
                            break

        print(f'Exported {exported} rows to {output_path}')
        return exported

    async def _fetch_batch(self, offset: int, remaining: Optional[int]) -> List[Dict[str, Any]]:
        batch_size = self.args.batch_size
        if remaining is not None:
            batch_size = min(batch_size, remaining)
        if batch_size <= 0:
            return []

        query, params = self._build_query(limit=batch_size, offset=offset)
        rows = await self.db.query_raw(query, *params)
        return list(rows or [])

    def _build_query(self, limit: int, offset: int) -> tuple[str, Sequence[Any]]:
        params: List[Any] = []
        where_clauses: List[str] = []

        def add_param(value: Any) -> str:
            params.append(value)
            return f'${len(params)}'

        start_dt = parse_datetime(self.args.start)
        end_dt = parse_datetime(self.args.end)
        if start_dt is not None:
            where_clauses.append(f'"startTime" >= {add_param(start_dt)}')
        if end_dt is not None:
            where_clauses.append(f'"startTime" < {add_param(end_dt)}')
        if self.args.model_group:
            where_clauses.append(f'model_group = {add_param(self.args.model_group)}')
        if self.args.team_id:
            where_clauses.append(f'team_id = {add_param(self.args.team_id)}')
        if self.args.deployment_id:
            placeholders = ', '.join(add_param(value) for value in self.args.deployment_id)
            where_clauses.append(f'model_id IN ({placeholders})')
        if self.args.status:
            placeholders = ', '.join(add_param(value) for value in self.args.status)
            where_clauses.append(f'status IN ({placeholders})')

        where_sql = ''
        if where_clauses:
            where_sql = 'WHERE ' + ' AND '.join(where_clauses)

        order = 'ASC' if self.args.order == 'asc' else 'DESC'
        limit_placeholder = add_param(limit)
        offset_placeholder = add_param(offset)
        query = f'''
            SELECT {', '.join(SELECT_COLUMNS)}
            FROM "LiteLLM_SpendLogs"
            {where_sql}
            ORDER BY "startTime" {order}, request_id {order}
            LIMIT {limit_placeholder}
            OFFSET {offset_placeholder}
        '''
        return query, params


async def async_main() -> int:
    args = parse_args()
    exporter = SpendLogExporter(args=args)
    return await exporter.run()


def main() -> int:
    return asyncio.run(async_main())


if __name__ == '__main__':
    sys.exit(main())
