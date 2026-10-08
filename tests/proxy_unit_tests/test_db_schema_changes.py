import pytest
import subprocess
import re
from typing import Dict, List, Set
from pathlib import Path


def get_schema_from_branch(branch: str = "main") -> str:
    """Get schema from specified git branch"""
    result = subprocess.run(
        ["git", "show", f"{branch}:schema.prisma"], capture_output=True, text=True
    )
    return result.stdout


def parse_model_fields(schema: str) -> Dict[str, Dict[str, str]]:
    """Parse Prisma schema into dict of models and their fields"""
    models = {}
    current_model = None

    for line in schema.split("\n"):
        line = line.strip()

        # Remove inline comments and skip comment / block attribute lines.
        if "//" in line:
            line = line.split("//", 1)[0].rstrip()
        if not line or line.startswith("@@"):
            continue

        # Find model definition
        if line.startswith("model "):
            current_model = line.split(" ")[1]
            models[current_model] = {}
            continue

        # Inside model definition
        if current_model and line and not line.startswith("}"):
            # Split field definition into name and type
            parts = line.split()
            if len(parts) >= 2:
                field_name = parts[0]
                field_type = " ".join(parts[1:])
                models[current_model][field_name] = field_type

        # End of model definition
        if line.startswith("}"):
            current_model = None

    return models


def get_model_block(schema: str, model_name: str) -> str:
    pattern = rf"model\s+{re.escape(model_name)}\s+\{{(.*?)\n\}}"
    match = re.search(pattern, schema, re.DOTALL)
    if not match:
        pytest.fail(f"Model {model_name} not found in schema")
    return match.group(1)


def check_breaking_changes(
    old_schema: Dict[str, Dict[str, str]], new_schema: Dict[str, Dict[str, str]]
) -> List[str]:
    """Check for breaking changes between schemas"""
    breaking_changes = []

    # Check each model in old schema
    for model_name, old_fields in old_schema.items():
        if model_name not in new_schema:
            breaking_changes.append(f"Breaking: Model {model_name} was removed")
            continue

        new_fields = new_schema[model_name]

        # Check each field in old model
        for field_name, old_type in old_fields.items():
            if field_name not in new_fields:
                breaking_changes.append(
                    f"Breaking: Field {model_name}.{field_name} was removed"
                )
                continue

            new_type = new_fields[field_name]

            # Check for type changes
            if old_type != new_type:
                # Check specific type changes that are breaking
                if "?" in old_type and "?" not in new_type:
                    breaking_changes.append(
                        f"Breaking: Field {model_name}.{field_name} changed from optional to required"
                    )
                if not old_type.startswith(new_type.split("?")[0]):
                    breaking_changes.append(
                        f"Breaking: Field {model_name}.{field_name} changed type from {old_type} to {new_type}"
                    )

    return breaking_changes


def test_aaaaaschema_compatibility():
    """Test if current schema has breaking changes compared to main"""
    import os

    print("Current directory:", os.getcwd())

    # Get schemas
    old_schema = get_schema_from_branch("main")
    with open("./schema.prisma", "r") as f:
        new_schema = f.read()

    # Parse schemas
    old_models = parse_model_fields(old_schema)
    new_models = parse_model_fields(new_schema)

    # Check for breaking changes
    breaking_changes = check_breaking_changes(old_models, new_models)

    # Fail if breaking changes found
    if breaking_changes:
        pytest.fail("\n".join(breaking_changes))

    # Print informational diff
    print("\nNon-breaking changes detected:")
    for model_name, new_fields in new_models.items():
        if model_name not in old_models:
            print(f"Added new model: {model_name}")
            continue

        for field_name, new_type in new_fields.items():
            if field_name not in old_models[model_name]:
                print(f"Added new field: {model_name}.{field_name}")


def test_mcp_server_schema_stays_in_sync_across_repo_copies():
    schema_paths = [
        Path("./schema.prisma"),
        Path("./litellm/proxy/schema.prisma"),
        Path("./litellm-proxy-extras/litellm_proxy_extras/schema.prisma"),
    ]
    expected_fields = {
        "source_url": "String?",
        "approval_status": 'String? @default("active")',
        "submitted_by": "String?",
        "submitted_at": "DateTime?",
        "reviewed_at": "DateTime?",
        "review_notes": "String?",
    }

    for schema_path in schema_paths:
        schema = schema_path.read_text()
        models = parse_model_fields(schema)
        mcp_fields = models["LiteLLM_MCPServerTable"]

        missing_or_mismatched = []
        for field_name, expected_definition in expected_fields.items():
            actual_definition = mcp_fields.get(field_name)
            if actual_definition != expected_definition:
                missing_or_mismatched.append(
                    f"{field_name}: expected `{expected_definition}`, got `{actual_definition}`"
                )

        if missing_or_mismatched:
            pytest.fail(
                f"{schema_path} MCP schema drift detected:\n"
                + "\n".join(missing_or_mismatched)
            )

        model_block = get_model_block(schema, "LiteLLM_MCPServerTable")
        assert "@@index([approval_status])" in model_block, (
            f"{schema_path} must keep @@index([approval_status]) so the MCP "
            "submission review queries do not drift from the runtime schema"
        )
