# Database Migration Runbook

This runbook is for LiteLLM proxy database migrations. It includes the normal happy path and the recovery steps we needed during the 2026-04-16 rehearsal against `litellm_test`.

## 2026-04-16 Rehearsal Summary

- Root cause: the three Prisma schema copies drifted on `LiteLLM_MCPServerTable`.
- Broken state:
  - `schema.prisma` was missing `source_url`, `approval_status`, `submitted_by`, `submitted_at`, `reviewed_at`, `review_notes`, and `@@index([approval_status])`.
  - `litellm/proxy/schema.prisma` already had the runtime shape.
  - `litellm-proxy-extras/litellm_proxy_extras/schema.prisma` had a stale variant (`approval_status @default("approved")`) and no `source_url`.
- Fix shipped in this repo:
  - synced all three `schema.prisma` files,
  - added `litellm-proxy-extras/litellm_proxy_extras/migrations/20260416210000_restore_mcp_submission_fields/`,
  - verified `prisma migrate diff` returns exit code `0` against:
    - `schema.prisma`
    - `litellm/proxy/schema.prisma`
    - `litellm-proxy-extras/litellm_proxy_extras/schema.prisma`

## Step 0: Sync All `schema.prisma` Files

There are multiple copies and they must stay identical:

| File | Purpose |
|------|---------|
| `schema.prisma` | Repo source of truth |
| `litellm/proxy/schema.prisma` | Proxy/runtime schema copy |
| `litellm-proxy-extras/litellm_proxy_extras/schema.prisma` | Migration generation + deploy schema |

Run this before generating or applying migrations:

```bash
diff schema.prisma litellm/proxy/schema.prisma
diff schema.prisma litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

If either diff is non-empty, fix the drift first. Do not generate or apply migrations until all three are aligned.

## Step 0.5: Remove Accidental `baseline_diff` Directories

`ProxyExtrasDBManager.setup_database(use_migrate=True)` runs a post-migration sanity check that may generate a temporary `*_baseline_diff` directory under `litellm-proxy-extras/litellm_proxy_extras/migrations/`.

These directories are not real migrations and must never be committed.

Check for leftovers:

```bash
find litellm-proxy-extras/litellm_proxy_extras/migrations -maxdepth 1 -type d -name '*baseline_diff'
```

Delete any leftovers before the next `migrate deploy`. If you leave them in place, Prisma will treat them as real migrations on the next run.

## Step 1: Pin Prisma CLI to `5.22.0`

Do not use the latest Prisma CLI for this workflow.

Reason:

- newer Prisma removed `--from-url`,
- the existing LiteLLM checks and rehearsal commands still rely on that flag.

Working pattern:

```bash
cat >/tmp/prisma-5.22.0 <<'SH'
#!/bin/sh
exec npx -y prisma@5.22.0 "$@"
SH
chmod +x /tmp/prisma-5.22.0

export PRISMA_CLI_PATH=/tmp/prisma-5.22.0
export NPM_CONFIG_CACHE=/tmp/prisma-npm-cache
export PRISMA_OFFLINE_MODE=true
```

## Step 2: Connect to the Target Database From Local Dev

Do not use the in-cluster DNS name directly from your Mac shell.

Use port-forward instead:

```bash
kubectl -n saas-guru port-forward service/postgresql-service 5432:5432
```

Then use a local URL:

```bash
export DATABASE_URL='postgresql://postgres:postgres123@127.0.0.1:5432/litellm_test'
```

If `5432` is occupied locally, use another local port and update `DATABASE_URL` accordingly.

## Step 3: Optional Backup

If you have local `pg_dump`, take a backup first.

If your workstation does not have `pg_dump` installed, run the backup from a pod or another environment that already has PostgreSQL client tools. Do not block the migration on local Homebrew setup.

## Step 4: Pre-Migration Diff

Before applying anything, verify whether the DB still drifts from the repo schema:

```bash
npx -y prisma@5.22.0 migrate diff \
  --from-url "$DATABASE_URL" \
  --to-schema-datamodel ./schema.prisma \
  --script --exit-code
echo $?
```

Interpretation:

- `0`: no drift
- `2`: schema drift exists; migration/update is still needed
- `1`: command failure, usually connectivity/tooling

## Step 5: Apply Migrations

The lightest reliable local rehearsal path is calling `PrismaManager.setup_database(use_migrate=True)` directly.

Use this when `litellm/proxy/prisma_migration.py` fails due missing proxy-only dependencies such as `orjson`.

```bash
PYTHONPATH="$PWD:$PWD/litellm-proxy-extras" \
NPM_CONFIG_CACHE=/tmp/prisma-npm-cache \
PRISMA_OFFLINE_MODE=true \
PRISMA_CLI_PATH=/tmp/prisma-5.22.0 \
python3 - <<'PY'
from litellm.proxy.db.prisma_client import PrismaManager
ok = PrismaManager.setup_database(use_migrate=True)
print("setup_database returned:", ok)
PY
```

Expected successful signal:

```text
All migrations have been successfully applied.
setup_database returned: True
```

## Step 6: Post-Migration Verification

Run all three checks. The migration is not done until all three are empty.

```bash
npx -y prisma@5.22.0 migrate diff \
  --from-url "$DATABASE_URL" \
  --to-schema-datamodel ./schema.prisma \
  --script --exit-code

npx -y prisma@5.22.0 migrate diff \
  --from-url "$DATABASE_URL" \
  --to-schema-datamodel ./litellm/proxy/schema.prisma \
  --script --exit-code

npx -y prisma@5.22.0 migrate diff \
  --from-url "$DATABASE_URL" \
  --to-schema-datamodel ./litellm-proxy-extras/litellm_proxy_extras/schema.prisma \
  --script --exit-code
```

Expected result for each:

```text
-- This is an empty migration.
```

And each command must exit with code `0`.

## Step 7: Recovery Guide

### `P1001`: Cannot Reach Database

This is almost always connectivity:

- port-forward is not running,
- wrong local port,
- `DATABASE_URL` still points at the in-cluster DNS name,
- or the target DB is temporarily unavailable.

Fix connectivity first. Do not change schema files because of a `P1001`.

### `P3018` On `*_baseline_diff`

If Prisma says a `*_baseline_diff` migration failed, that usually means a temporary rehearsal artifact was left under `litellm-proxy-extras/litellm_proxy_extras/migrations/`.

Recovery:

1. Delete the accidental `*_baseline_diff` directory from the repo.
2. Re-run the migration flow.
3. If the failed migration was already recorded in `_prisma_migrations`, resolve it before retrying.

The 2026-04-16 rehearsal hit exactly this failure mode.

### `ImportError: Missing dependency No module named 'orjson'`

This comes from using `litellm/proxy/prisma_migration.py` without the full proxy extras installed locally.

Use the direct `PrismaManager.setup_database(use_migrate=True)` invocation from Step 5 instead.

## Release Gate: When Is It Safe to Build a New Image?

Safe to build and push a test image only when all of the following are true:

1. `schema.prisma`, `litellm/proxy/schema.prisma`, and `litellm-proxy-extras/litellm_proxy_extras/schema.prisma` are in sync.
2. No accidental `*_baseline_diff` directory is left under `litellm-proxy-extras/litellm_proxy_extras/migrations/`.
3. `PrismaManager.setup_database(use_migrate=True)` succeeds against the target DB.
4. All three post-migration diff commands return exit code `0`.
5. The repo contains the intended real migration directory for the change.

## Current MCP Migration

The MCP submission workflow fix in this branch is:

- schema sync for `LiteLLM_MCPServerTable` across all three schema copies,
- restore `source_url`,
- restore `approval_status`, `submitted_by`, `submitted_at`, `reviewed_at`, `review_notes`,
- restore `@@index([approval_status])`,
- normalize `approval_status` default back to `"active"`,
- real migration: `20260416210000_restore_mcp_submission_fields`

---

After the migration is verified and the repo is clean, continue with [build_and_publish.md](./build_and_publish.md) if you need to publish a new `litellm-proxy-extras` package.
