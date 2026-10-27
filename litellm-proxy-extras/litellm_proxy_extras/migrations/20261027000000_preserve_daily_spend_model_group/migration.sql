-- Keep the 20260525 public-model dimension in the v1.106.4 bulk writer.
-- An existing correct index is retained. Historical migrations/checksums are
-- never rewritten, and historical NULL rows and already aggregated spend are
-- deliberately left intact. New writes normalize missing model_group to ''.
DO $$
DECLARE
    item RECORD;
    idx RECORD;
    key_columns TEXT[];
    old_columns TEXT[];
    correct_index TEXT;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('LiteLLM_DailyUserSpend', 'user_id', 'LiteLLM_DailyUserSpend_user_id_date_api_key_model_custom_ll_key'),
        ('LiteLLM_DailyTeamSpend', 'team_id', 'LiteLLM_DailyTeamSpend_team_id_date_api_key_model_custom_ll_key'),
        ('LiteLLM_DailyOrganizationSpend', 'organization_id', 'LiteLLM_DailyOrganizationSpend_organization_id_date_api_key_key'),
        ('LiteLLM_DailyEndUserSpend', 'end_user_id', 'LiteLLM_DailyEndUserSpend_end_user_id_date_api_key_model_cu_key'),
        ('LiteLLM_DailyAgentSpend', 'agent_id', 'LiteLLM_DailyAgentSpend_agent_id_date_api_key_model_custom__key'),
        ('LiteLLM_DailyTagSpend', 'tag', 'LiteLLM_DailyTagSpend_tag_date_api_key_model_custom_llm_pro_key')
    ) AS tables(table_name, entity_column, index_name)
    LOOP
        key_columns := ARRAY[item.entity_column, 'date', 'api_key', 'model', 'model_group',
                             'custom_llm_provider', 'mcp_namespaced_tool_name', 'endpoint'];
        old_columns := array_remove(key_columns, 'model_group');
        correct_index := NULL;
        EXECUTE format('ALTER TABLE %I ALTER COLUMN model_group SET DEFAULT %L', item.table_name, '');

        FOR idx IN
            SELECT c.relname AS name, i.indisvalid,
                   ARRAY(SELECT a.attname::TEXT
                         FROM unnest(i.indkey::SMALLINT[]) WITH ORDINALITY AS k(attnum, position)
                         JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = k.attnum
                         ORDER BY k.position) AS columns,
                   constraint_row.conname AS constraint_name
            FROM pg_index i
            JOIN pg_class c ON c.oid = i.indexrelid
            LEFT JOIN pg_constraint constraint_row ON constraint_row.conindid = i.indexrelid
            WHERE i.indrelid = to_regclass(format('%I', item.table_name))
              AND i.indisunique AND i.indpred IS NULL AND i.indexprs IS NULL
        LOOP
            IF idx.columns = old_columns THEN
                IF idx.constraint_name IS NOT NULL THEN
                    EXECUTE format('ALTER TABLE %I DROP CONSTRAINT %I', item.table_name, idx.constraint_name);
                ELSE
                    EXECUTE format('DROP INDEX %I', idx.name);
                END IF;
            ELSIF idx.columns = key_columns AND idx.indisvalid
                  AND (correct_index IS NULL OR idx.name = item.index_name) THEN
                correct_index := idx.name;
            END IF;
        END LOOP;

        IF correct_index IS NULL THEN
            EXECUTE format('CREATE UNIQUE INDEX %I ON %I (%s)', item.index_name, item.table_name,
                           (SELECT string_agg(format('%I', col), ', ') FROM unnest(key_columns) AS col));
        ELSIF correct_index <> item.index_name THEN
            EXECUTE format('ALTER INDEX %I RENAME TO %I', correct_index, item.index_name);
        END IF;
    END LOOP;
END $$;
