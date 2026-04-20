-- Restore MCP submission workflow fields that were dropped by an accidental schema sync.
-- Keep this migration idempotent so it is safe on databases that already have some or all columns.
ALTER TABLE "LiteLLM_MCPServerTable"
  ADD COLUMN IF NOT EXISTS "source_url" TEXT,
  ADD COLUMN IF NOT EXISTS "approval_status" TEXT DEFAULT 'active',
  ADD COLUMN IF NOT EXISTS "submitted_by" TEXT,
  ADD COLUMN IF NOT EXISTS "submitted_at" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "reviewed_at" TIMESTAMP(3),
  ADD COLUMN IF NOT EXISTS "review_notes" TEXT;

ALTER TABLE "LiteLLM_MCPServerTable"
  ALTER COLUMN "approval_status" DROP NOT NULL,
  ALTER COLUMN "approval_status" SET DEFAULT 'active';

UPDATE "LiteLLM_MCPServerTable"
SET "approval_status" = 'active'
WHERE "approval_status" IS NULL OR "approval_status" = 'approved';

CREATE INDEX IF NOT EXISTS "LiteLLM_MCPServerTable_approval_status_idx"
  ON "LiteLLM_MCPServerTable"("approval_status");
