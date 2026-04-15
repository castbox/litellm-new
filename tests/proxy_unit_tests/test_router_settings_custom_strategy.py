import asyncio
import importlib.metadata
import json
import sys
import types
from unittest.mock import AsyncMock, MagicMock

from fastapi import APIRouter

orjson_stub = types.ModuleType("orjson")
orjson_stub.dumps = lambda obj, *args, **kwargs: json.dumps(obj).encode("utf-8")
orjson_stub.loads = lambda data, *args, **kwargs: json.loads(data)
sys.modules.setdefault("orjson", orjson_stub)

python_multipart_stub = types.ModuleType("python_multipart")
python_multipart_stub.__version__ = "0.0.13"
sys.modules.setdefault("python_multipart", python_multipart_stub)

multipart_stub = types.ModuleType("multipart")
multipart_stub.__version__ = "0.0.13"
sys.modules.setdefault("multipart", multipart_stub)

multipart_submodule_stub = types.ModuleType("multipart.multipart")
multipart_submodule_stub.parse_options_header = lambda value: (value, {})
sys.modules.setdefault("multipart.multipart", multipart_submodule_stub)

email_validator_stub = types.ModuleType("email_validator")
email_validator_stub.validate_email = (
    lambda email, *args, **kwargs: types.SimpleNamespace(email=email)
)
email_validator_stub.EmailNotValidError = ValueError
sys.modules.setdefault("email_validator", email_validator_stub)

original_version = importlib.metadata.version


def _patched_version(package_name: str) -> str:
    if package_name == "email-validator":
        return "2.0.0"
    return original_version(package_name)


importlib.metadata.version = _patched_version

try:
    import pydantic.networks as pydantic_networks

    pydantic_networks.version = _patched_version
    pydantic_networks.import_email_validator = lambda: None
    pydantic_networks.email_validator = email_validator_stub
except Exception:
    pass

fastapi_sso_stub = types.ModuleType("fastapi_sso")
fastapi_sso_sso_stub = types.ModuleType("fastapi_sso.sso")
fastapi_sso_base_stub = types.ModuleType("fastapi_sso.sso.base")


class _OpenID:
    def __init__(self, *args, **kwargs):
        pass


fastapi_sso_base_stub.OpenID = _OpenID
sys.modules.setdefault("fastapi_sso", fastapi_sso_stub)
sys.modules.setdefault("fastapi_sso.sso", fastapi_sso_sso_stub)
sys.modules.setdefault("fastapi_sso.sso.base", fastapi_sso_base_stub)

ui_sso_stub = types.ModuleType("litellm.proxy.management_endpoints.ui_sso")
ui_sso_stub.router = APIRouter()
ui_sso_stub.get_disabled_non_admin_personal_key_creation = (
    lambda *args, **kwargs: False
)
sys.modules.setdefault("litellm.proxy.management_endpoints.ui_sso", ui_sso_stub)


def test_router_settings_helpers_include_custom_routing_strategy_option():
    from litellm.proxy.management_endpoints.router_settings_endpoints import (
        _get_custom_routing_strategies,
        _get_routing_strategy_options,
    )

    custom_routing_strategies = _get_custom_routing_strategies()
    combined_routing_strategies = _get_routing_strategy_options()

    assert custom_routing_strategies == ["cost-latency-balanced"]
    assert "cost-latency-balanced" in combined_routing_strategies


def test_add_router_settings_from_db_config_applies_config_only_custom_strategy():
    from litellm.proxy.proxy_server import ProxyConfig

    proxy_config = ProxyConfig()
    mock_router = MagicMock()
    mock_router.update_settings = MagicMock()
    config_data = {
        "router_settings": {
            "routing_strategy": "simple-shuffle",
            "custom_routing_strategy": "cost-latency-balanced",
            "custom_routing_strategy_args": {
                "default_routing_mode": "balanced",
                "per_model_group_routing": {"ai-seek-fast-small": "latency-first"},
            },
        }
    }

    asyncio.run(
        proxy_config._add_router_settings_from_db_config(
            config_data=config_data,
            llm_router=mock_router,
            prisma_client=None,
        )
    )

    mock_router.update_settings.assert_called_once_with(**config_data["router_settings"])
