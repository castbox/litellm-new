---
name: add-gemini-provider
description: 添加gemini协议的供应商
---

# Process

本文档描述如何在 LiteLLM 中添加一个使用 Gemini 协议的新供应商。

## 信息收集

在开始之前，请向用户确认以下信息：

1. **供应商名称**（小写下划线格式）
   - 例如：`deerapi_gemini`
   - 用于代码中的标识符

2. **供应商显示名称**
   - 例如：`DeerAPI Gemini`
   - 用于 UI 显示

3. **API Base URL**
   - 例如：`https://api.deerapi.com/v1beta`
   - 供应商的 API 端点

4. **API 域名**（用于自动检测）
   - 例如：`api.deerapi.com/v1beta`
   - 从 API Base 提取的域名路径

5. **环境变量前缀**
   - 例如：`DEERAPI_GEMINI`
   - 用于 `{PREFIX}_API_KEY` 和 `{PREFIX}_API_BASE`

6. **默认模型名称**
   - 例如：`gemini-2.0-flash`
   - UI 中的占位符

7. **Logo 文件名**（如果有）
   - 例如：`deerapi.jpeg`
   - 放在 `ui/litellm-dashboard/public/logos/` 目录

## 前置条件

- 新供应商使用 Gemini 协议（与 Google AI Studio Gemini 兼容）
- 只需要自定义 API Base 和 API Key 获取逻辑

## 重要修复

在开始添加新供应商之前，如果项目存在 issue #19184 相关的 bug，需要先修复：

**文件: `litellm/llms/custom_httpx/aiohttp_transport.py`**

在 `_make_aiohttp_request` 方法中，移除 `ClientTimeout` 的 `total` 参数：

```python
# 修复前
timeout=ClientTimeout(
    total=timeout.get("read"),  # ❌ 需要移除这一行
    sock_connect=timeout.get("connect"),
    sock_read=timeout.get("read"),
    connect=timeout.get("pool"),
),

# 修复后
timeout=ClientTimeout(
    sock_connect=timeout.get("connect"),
    sock_read=timeout.get("read"),
    connect=timeout.get("pool"),
),
```

**为什么**: `stream_timeout` 应该只控制单个 chunk 的超时，而不是整个 stream 的持续时间。设置 `total` 会导致整个流在读取超时后中断，而不是只对单个 chunk 应用超时。

## 步骤

### 1. 创建供应商配置类

创建目录结构：
```
litellm/llms/{provider_name}/
├── __init__.py
├── chat/
│   ├── __init__.py
│   └── transformation.py
└── cost_calculator.py
```

**文件: `litellm/llms/{provider_name}/chat/transformation.py`**

```python
from typing import Optional
from litellm.llms.gemini.chat.transformation import GoogleAIStudioGeminiConfig
from litellm.secret_managers.main import get_secret_str

class {ProviderName}Config(GoogleAIStudioGeminiConfig):
    """
    继承 GoogleAIStudioGeminiConfig，复用所有 Gemini 协议实现，
    只覆盖 API Base 和 API Key 获取逻辑。
    """

    @staticmethod
    def get_api_base(api_base: Optional[str] = None) -> str:
        return (
            api_base
            or get_secret_str("{PROVIDER}_API_BASE")
            or "https://your-default-api-base.com/v1beta"
        )

    @staticmethod
    def get_api_key(api_key: Optional[str] = None) -> Optional[str]:
        return (
            api_key
            or get_secret_str("{PROVIDER}_API_KEY")
        )
```

**为什么**: 继承 `GoogleAIStudioGeminiConfig` 可以复用所有 Gemini 协议的参数映射、消息转换等逻辑，只需覆盖 API 端点配置。

**文件: `litellm/llms/{provider_name}/cost_calculator.py`**

```python
from typing import Tuple
from litellm.litellm_core_utils.llm_cost_calc.utils import generic_cost_per_token
from litellm.types.utils import Usage

def cost_per_token(model: str, usage: Usage) -> Tuple[float, float]:
    return generic_cost_per_token(
        model=model, usage=usage, custom_llm_provider="{provider_name}"
    )
```

**为什么**: 让成本按供应商独立统计，便于分析不同供应商的使用成本。

### 2. 注册到 LlmProviders 枚举

**文件: `litellm/types/utils.py`**

在 `LlmProviders` 枚举中添加新供应商：

```python
class LlmProviders(str, Enum):
    # ... 其他供应商
    {PROVIDER_NAME} = "{provider_name}"
```

**为什么**: `LlmProviders` 枚举用于验证供应商名称的合法性。如果不添加，从数据库加载模型时会因为供应商验证失败而被过滤掉。

### 3. 导出配置类

**文件: `litellm/__init__.py`**

```python
from .llms.{provider_name}.chat.transformation import {ProviderName}Config
```

**为什么**: 让其他模块可以通过 `litellm.{ProviderName}Config` 访问配置类。

### 4. 注册支持的 OpenAI 参数

**文件: `litellm/litellm_core_utils/get_supported_openai_params.py`**

在 `get_supported_openai_params` 函数中添加：

```python
elif custom_llm_provider == "{provider_name}":
    return litellm.{ProviderName}Config().get_supported_openai_params(
        model=model
    )
```

**为什么**: 告诉 LiteLLM 这个供应商支持哪些 OpenAI 参数（如 `temperature`, `max_tokens`, `reasoning_effort` 等）。如果不注册，参数会被放入 `extra_body` 而不是正确映射。

### 5. 注册参数映射逻辑

**文件: `litellm/utils.py`**

在 `get_optional_params` 函数中添加：

```python
elif custom_llm_provider == "{provider_name}":
    optional_params = litellm.{ProviderName}Config().map_openai_params(
        non_default_params=non_default_params,
        optional_params=optional_params,
        model=model,
        drop_params=(
            drop_params
            if drop_params is not None and isinstance(drop_params, bool)
            else False
        ),
    )
```

**为什么**: 将 OpenAI 格式的参数（如 `reasoning_effort`）映射为 Gemini 格式（如 `thinkingConfig.thinkingLevel`）。

### 6. 添加供应商检测逻辑

**文件: `litellm/litellm_core_utils/get_llm_provider_logic.py`**

添加两处检测：

1. 基于 API Base 域名检测（在 `openai_compatible_endpoints` 循环中）：
```python
elif endpoint == "your-api-domain.com/v1beta":
    custom_llm_provider = "{provider_name}"
    dynamic_api_key = get_secret_str("{PROVIDER}_API_KEY")
```

**注意**: 这段代码放在 `openai_compatible_endpoints` 循环中，但 Gemini 协议端点**不需要**添加到 `openai_compatible_endpoints` 列表（`litellm/constants.py`），因为它不是 OpenAI 兼容协议。此检测逻辑作为备用，主要依靠模型前缀检测。

2. 基于模型前缀检测：
```python
elif model.startswith("{provider_name}/"):
    custom_llm_provider = "{provider_name}"
```

**为什么**: 让 LiteLLM 能够根据 API Base 或模型名称自动识别供应商。对于 Gemini 协议供应商，主要依靠模型前缀检测。

### 7. 添加 completion 处理逻辑

**文件: `litellm/main.py`**

在 `completion` 函数中添加供应商处理分支：

```python
elif custom_llm_provider == "{provider_name}":
    from litellm.llms.{provider_name}.chat.transformation import {ProviderName}Config

    api_key = {ProviderName}Config.get_api_key(api_key) or litellm.api_key
    api_base = {ProviderName}Config.get_api_base(api_base)
    gemini_api_key = api_key

    new_params = safe_deep_copy(optional_params or {})
    response = vertex_chat_completion.completion(
        model=model,
        messages=messages,
        custom_llm_provider="gemini",  # 使用 gemini 协议
        model_response=model_response,
        print_verbose=print_verbose,
        optional_params=new_params,
        litellm_params=litellm_params,
        timeout=timeout,
        encoding=_get_encoding(),
        logging_obj=logging,
        acompletion=acompletion,
        api_base=api_base,
        gemini_api_key=gemini_api_key,
        vertex_project=None,
        vertex_location=None,
        vertex_credentials=None,
        extra_headers=headers,
        client=client,
        logger_fn=logger_fn,
    )
```

**为什么**: 这是实际调用 API 的入口。通过设置 `custom_llm_provider="gemini"` 复用 Gemini 协议的请求处理逻辑。

### 8. 注册成本计算

**文件: `litellm/cost_calculator.py`**

在 `cost_per_token` 函数中添加：

```python
elif custom_llm_provider == "{provider_name}":
    from litellm.llms.{provider_name}.cost_calculator import (
        cost_per_token as {provider_name}_cost_per_token,
    )
    return {provider_name}_cost_per_token(model=model, usage=usage_block)
```

**为什么**: 让 LiteLLM 能够计算该供应商的 API 调用成本，便于成本分析和预算控制。

### 9. 添加 UI 供应商配置

**文件: `litellm/proxy/public_endpoints/provider_create_fields.json`**

```json
{
  "provider": "{provider_name}",
  "provider_display_name": "Your Provider Name",
  "litellm_provider": "{provider_name}",
  "credential_fields": [
    {
      "key": "api_base",
      "label": "API Base",
      "placeholder": "https://your-api-base.com/v1beta",
      "required": false,
      "field_type": "text",
      "default_value": "https://your-api-base.com/v1beta"
    },
    {
      "key": "api_key",
      "label": "API Key",
      "required": true,
      "field_type": "password"
    }
  ],
  "default_model_placeholder": "gemini-2.0-flash"
}
```

**重要**: `provider` 字段必须使用小写下划线格式（如 `deerapi_gemini`），与 `LlmProviders` 枚举值完全一致。不要使用空格或连字符。

**为什么**: 让供应商出现在 LiteLLM Dashboard 的添加模型下拉菜单中。

**文件: `ui/litellm-dashboard/src/components/provider_info_helpers.tsx`**

1. 在 `Providers` 枚举中添加：
```typescript
export enum Providers {
  // ... 其他供应商
  {ProviderName} = "Your Provider Display Name",
}
```

2. 在 `provider_map` 中添加映射：
```typescript
export const provider_map: Record<string, string> = {
  // ... 其他映射
  {ProviderName}: "{provider_name}",
}
```

3. 在 `providerLogoMap` 中添加 logo（复用同系列供应商的 logo）：
```typescript
export const providerLogoMap: Record<string, string> = {
  // ... 其他 logo
  [Providers.{ProviderName}]: `${asset_logos_folder}your-logo.png`,
}
```

**注意**: 对于 Gemini 协议供应商（如 `OminiLink_Gemini`），应复用其基础供应商的 logo（如 `omnilink.png`）。

**为什么**: UI 组件使用这些枚举和映射来显示供应商名称和 logo。

### 10. 重新构建 UI

```bash
cd ui/litellm-dashboard
npm run build
cp -r out/* ../../litellm/proxy/_experimental/out/
rm -rf /tmp/litellm_ui  # 清除 UI 缓存
```

**为什么**:
- `npm run build` 将 UI 打包到 `ui/litellm-dashboard/out/` 目录
- `cp -r out/* ../../litellm/proxy/_experimental/out/` 将打包结果复制到 proxy 服务的 UI 静态文件目录
- `rm -rf /tmp/litellm_ui` 清除 UI 缓存，否则 LiteLLM 会使用旧的缓存文件

### 11. 本地启动服务验证

```bash
poetry run litellm --config ../guru-litellm/configs/proxy_config_local.yaml --debug --detailed_debug
```

**为什么**: 启动本地服务验证新供应商是否正常工作，`--debug --detailed_debug` 可以查看详细日志便于排查问题。

## 常见问题

### 模型从数据库加载后不显示

检查 `LlmProviders` 枚举是否包含该供应商。

### 参数没有正确传递给 API

检查是否在 `get_supported_openai_params.py` 和 `utils.py` 中注册了供应商。

### UI 下拉菜单看不到供应商

1. 检查 `provider_create_fields.json` 是否添加了配置
2. 确保 `provider` 字段使用小写下划线格式
3. 重新构建 UI 并清除 `/tmp/litellm_ui` 缓存

### 创建模型时报 "Unsupported provider"

检查 credentials 创建时使用的 provider 名称是否与 `LlmProviders` 枚举值一致（使用下划线而非连字符）。

## 文件变更汇总

### 新建文件（4 个）

| 文件路径 | 说明 |
|---------|------|
| `litellm/llms/{provider_name}/__init__.py` | 模块初始化 |
| `litellm/llms/{provider_name}/chat/__init__.py` | chat 模块初始化，导出配置类 |
| `litellm/llms/{provider_name}/chat/transformation.py` | 供应商配置类，继承 GoogleAIStudioGeminiConfig |
| `litellm/llms/{provider_name}/cost_calculator.py` | 成本计算器 |

### 修改文件（9 个）

| 文件路径 | 修改内容 | 步骤 |
|---------|---------|------|
| `litellm/types/utils.py` | 在 `LlmProviders` 枚举中添加供应商 | 2 |
| `litellm/__init__.py` | 导出配置类 | 3 |
| `litellm/litellm_core_utils/get_supported_openai_params.py` | 注册支持的 OpenAI 参数 | 4 |
| `litellm/utils.py` | 在 `get_optional_params` 中添加参数映射 | 5 |
| `litellm/litellm_core_utils/get_llm_provider_logic.py` | 添加供应商检测逻辑 | 6 |
| `litellm/main.py` | 在 `completion` 函数中添加处理分支 | 7 |
| `litellm/cost_calculator.py` | 注册成本计算函数 | 8 |
| `litellm/proxy/public_endpoints/provider_create_fields.json` | 添加 UI 供应商配置 | 9 |
| `ui/litellm-dashboard/src/components/provider_info_helpers.tsx` | 在 `Providers` 枚举、`provider_map` 和 `providerLogoMap` 中添加供应商 | 9 |
