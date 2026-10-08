-- Daily spend aggregation must distinguish public model names (model_group).
-- A single provider model/deployment can back multiple model_groups, so omitting
-- model_group from the unique key merges those public-model metrics together.

-- Normalize future rows without a model_group to an empty string so the unique
-- indexes behave consistently for null/empty public model names.
ALTER TABLE "LiteLLM_DailyAgentSpend" ALTER COLUMN "model_group" SET DEFAULT '';
ALTER TABLE "LiteLLM_DailyEndUserSpend" ALTER COLUMN "model_group" SET DEFAULT '';
ALTER TABLE "LiteLLM_DailyOrganizationSpend" ALTER COLUMN "model_group" SET DEFAULT '';
ALTER TABLE "LiteLLM_DailyTagSpend" ALTER COLUMN "model_group" SET DEFAULT '';
ALTER TABLE "LiteLLM_DailyTeamSpend" ALTER COLUMN "model_group" SET DEFAULT '';
ALTER TABLE "LiteLLM_DailyUserSpend" ALTER COLUMN "model_group" SET DEFAULT '';

-- Drop old unique indexes that did not include model_group.
DROP INDEX IF EXISTS "LiteLLM_DailyAgentSpend_agent_id_date_api_key_model_custom__key";
DROP INDEX IF EXISTS "LiteLLM_DailyEndUserSpend_end_user_id_date_api_key_model_cu_key";
DROP INDEX IF EXISTS "LiteLLM_DailyOrganizationSpend_organization_id_date_api_key_key";
DROP INDEX IF EXISTS "LiteLLM_DailyTagSpend_tag_date_api_key_model_custom_llm_pro_key";
DROP INDEX IF EXISTS "LiteLLM_DailyTeamSpend_team_id_date_api_key_model_custom_ll_key";
DROP INDEX IF EXISTS "LiteLLM_DailyUserSpend_user_id_date_api_key_model_custom_ll_key";

-- Recreate unique indexes with model_group included.
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyAgentSpend_agent_id_date_api_key_model_custom__key" ON "LiteLLM_DailyAgentSpend"("agent_id", "date", "api_key", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyEndUserSpend_end_user_id_date_api_key_model_cu_key" ON "LiteLLM_DailyEndUserSpend"("end_user_id", "date", "api_key", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyOrganizationSpend_organization_id_date_api_key_key" ON "LiteLLM_DailyOrganizationSpend"("organization_id", "date", "api_key", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyTagSpend_tag_date_api_key_model_custom_llm_pro_key" ON "LiteLLM_DailyTagSpend"("tag", "date", "api_key", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyTeamSpend_team_id_date_api_key_model_custom_ll_key" ON "LiteLLM_DailyTeamSpend"("team_id", "date", "api_key", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");
CREATE UNIQUE INDEX IF NOT EXISTS "LiteLLM_DailyUserSpend_user_id_date_api_key_model_custom_ll_key" ON "LiteLLM_DailyUserSpend"("user_id", "date", "api_key", "model", "model_group", "custom_llm_provider", "mcp_namespaced_tool_name", "endpoint");
