---
name: add-openai-provider
description: 添加 OpenAI 兼容协议的供应商
---

# Process

本文档描述如何在 LiteLLM 中添加一个使用 OpenAI 兼容协议的新供应商。

## 信息收集

在开始之前，请向用户确认以下信息：

1. **供应商名称**（小写下划线格式）
   - 例如：`deerapi`
   - 用于代码中的标识符

2. **供应商显示名称**
   - 例如：`DeerAPI`
   - 用于 UI 显示和枚举值

3. **API Base URL**
   - 例如：`https://api.deerapi.com/v1`
   - 供应商的 API 端点

4. **API 域名路径**（用于自动检测）
   - 例如：`api.deerapi.com/v1`
   - 从 API Base 提取的域名路径，添加到 `openai_compatible_endpoints` 列表

5. **环境变量名称**
   - API Key 环境变量：例如 `DEERAPI_API_KEY`、`DEER_API_KEY`
   - API Base 环境变量：例如 `DEERAPI_API_BASE`

6. **默认模型名称**
   - 例如：`gpt-3.5-turbo`
   - UI 中的占位符

7. **Logo 文件名**（如果有）
   - 例如：`deerapi.jpeg`
   - 放在 `ui/litellm-dashboard/public/assets/logos/` 目录

## 前置条件

- 新供应商使用 OpenAI 兼容协议（`/v1/chat/completions` 等标准端点）
- 需要自定义 API Base 和 API Key 获取逻辑

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

### 1. 添加到常量配置

**文件: `litellm/constants.py`**

添加到以下列表：

```python
# 1. LITELLM_CHAT_PROVIDERS 列表
LITELLM_CHAT_PROVIDERS: List = [
    # ... 其他供应商
    "{provider_name}",
]

# 2. openai_compatible_endpoints 列表
openai_compatible_endpoints: List = [
    # ... 其他端点
    "https://{api_domain}/v1",
]

# 3. openai_compatible_providers 列表
openai_compatible_providers: List = [
    # ... 其他供应商
    "{provider_name}",
]
```

**为什么**:
- `LITELLM_CHAT_PROVIDERS` 声明这是一个聊天供应商
- `openai_compatible_endpoints` 用于根据 API Base 自动检测供应商
- `openai_compatible_providers` 声明这是一个 OpenAI 兼容供应商

### 2. 注册到 LlmProviders 枚举

**文件: `litellm/types/utils.py`**

在 `LlmProviders` 枚举中添加新供应商：

```python
class LlmProviders(str, Enum):
    # ... 其他供应商
    {PROVIDER_NAME} = "{provider_name}"
```

**为什么**: `LlmProviders` 枚举用于验证供应商名称的合法性。如果不添加，从数据库加载模型时会因为供应商验证失败而被过滤掉。

### 3. 创建供应商配置类

创建目录结构：
```
litellm/llms/{provider_name}/
├── __init__.py
└── chat/
    ├── __init__.py
    └── transformation.py
```

**文件: `litellm/llms/{provider_name}/__init__.py`**
```python
"""{ProviderDisplayName} provider implementation"""
```

**文件: `litellm/llms/{provider_name}/chat/__init__.py`**
```python
from .transformation import {ProviderName}ChatConfig

__all__ = ["{ProviderName}ChatConfig"]
```

**文件: `litellm/llms/{provider_name}/chat/transformation.py`**

```python
"""
Translates from OpenAI's `/v1/chat/completions` to {ProviderDisplayName}'s `/v1/chat/completions`
"""
from typing import Optional, Tuple
from litellm.secret_managers.main import get_secret_str
from ...openai.chat.gpt_transformation import OpenAIGPTConfig


class {ProviderName}ChatConfig(OpenAIGPTConfig):
    def _get_openai_compatible_provider_info(
        self, api_base: Optional[str], api_key: Optional[str]
    ) -> Tuple[Optional[str], Optional[str]]:
        api_base = (
            api_base
            or get_secret_str("{PROVIDER}_API_BASE")
            or "{default_api_base}"
        )
        dynamic_api_key = (
            api_key
            or get_secret_str("{PROVIDER}_API_KEY")
        )
        return api_base, dynamic_api_key
```

**为什么**: 继承 `OpenAIGPTConfig` 可以复用所有 OpenAI 兼容协议的参数映射和请求处理逻辑，只需覆盖 API 端点配置。

### 4. 导出配置类

**文件: `litellm/__init__.py`**

添加导入语句：
```python
from .llms.{provider_name}.chat.transformation import {ProviderName}ChatConfig
```

添加 API key 变量（在其他 `xxx_key` 变量附近）：
```python
{provider_name}_key: Optional[str] = None
```

添加模型集合变量（在其他 `xxx_models` 变量附近）：
```python
{provider_name}_models: Set = set()
```

在 `add_known_models()` 函数中添加处理逻辑：
```python
elif value.get("litellm_provider") == "{provider_name}":
    {provider_name}_models.add(key)
```

在 `models_by_provider` 字典中添加映射：
```python
models_by_provider: dict = {
    # ... 其他映射
    "{provider_name}": {provider_name}_models,
}
```

**为什么**: 让其他模块可以通过 `litellm.{ProviderName}ChatConfig` 访问配置类，并支持模型集合管理。

### 5. 添加供应商检测逻辑

**文件: `litellm/litellm_core_utils/get_llm_provider_logic.py`**

1. 在 `openai_compatible_endpoints` 循环中添加端点检测：
```python
elif endpoint == "{api_domain}/v1":
    custom_llm_provider = "{provider_name}"
    dynamic_api_key = get_secret_str("{PROVIDER}_API_KEY")
```

2. 添加模型前缀检测：
```python
elif model.startswith("{provider_name}/"):
    custom_llm_provider = "{provider_name}"
```

3. 在 `_get_openai_compatible_provider_info` 函数中添加配置类调用：
```python
elif custom_llm_provider == "{provider_name}":
    (
        api_base,
        dynamic_api_key,
    ) = litellm.{ProviderName}ChatConfig()._get_openai_compatible_provider_info(
        api_base, api_key
    )
```

**为什么**: 让 LiteLLM 能够根据 API Base 或模型名称自动识别供应商，并获取正确的 API 配置。

### 6. 添加 completion 处理逻辑

**文件: `litellm/main.py`**

在 `completion` 函数中添加供应商处理分支：

```python
elif custom_llm_provider == "{provider_name}":
    api_key = (
        api_key
        or litellm.{provider_name}_key
        or get_secret_str("{PROVIDER}_API_KEY")
        or litellm.api_key
    )

    api_base = (
        api_base
        or litellm.api_base
        or get_secret_str("{PROVIDER}_API_BASE")
        or "{default_api_base}"
    )

    response = base_llm_http_handler.completion(
        model=model,
        messages=messages,
        headers=headers,
        model_response=model_response,
        api_key=api_key,
        api_base=api_base,
        acompletion=acompletion,
        logging_obj=logging,
        optional_params=optional_params,
        litellm_params=litellm_params,
        timeout=timeout,
        client=client,
        custom_llm_provider=custom_llm_provider,
        encoding=encoding,
        stream=stream,
        provider_config=provider_config,
    )
```

**为什么**: 这是实际调用 API 的入口。使用 `base_llm_http_handler.completion` 处理 OpenAI 兼容协议的请求。

### 7. 添加 UI 供应商配置

**文件: `litellm/proxy/public_endpoints/provider_create_fields.json`**

```json
{
  "provider": "{ProviderDisplayName}",
  "provider_display_name": "{ProviderDisplayName}",
  "litellm_provider": "{provider_name}",
  "credential_fields": [
    {
      "key": "api_base",
      "label": "API Base",
      "placeholder": "{default_api_base}",
      "tooltip": null,
      "required": false,
      "field_type": "text",
      "options": null,
      "default_value": "{default_api_base}"
    },
    {
      "key": "api_key",
      "label": "{ProviderDisplayName} API Key",
      "placeholder": null,
      "tooltip": null,
      "required": true,
      "field_type": "password",
      "options": null,
      "default_value": null
    }
  ],
  "default_model_placeholder": "gpt-3.5-turbo"
}
```

**为什么**: 让供应商出现在 LiteLLM Dashboard 的添加模型下拉菜单中。

**文件: `ui/litellm-dashboard/src/components/provider_info_helpers.tsx`**

1. 在 `Providers` 枚举中添加：
```typescript
export enum Providers {
  // ... 其他供应商
  {ProviderName} = "{ProviderDisplayName}",
}
```

2. 在 `provider_map` 中添加映射：
```typescript
export const provider_map: Record<string, string> = {
  // ... 其他映射
  {ProviderName}: "{provider_name}",
}
```

3. 在 `providerLogoMap` 中添加 logo：
```typescript
export const providerLogoMap: Record<string, string> = {
  // ... 其他 logo
  [Providers.{ProviderName}]: `${asset_logos_folder}{logo_filename}`,
}
```

**为什么**: UI 组件使用这些枚举和映射来显示供应商名称和 logo。

### 8. 重新构建 UI

```bash
cd ui/litellm-dashboard
npm run build
cp -r out/* ../../litellm/proxy/_experimental/out/
rm -rf /tmp/litellm_ui  # 清除 UI 缓存
```

**为什么**:
- `npm run build` 将 UI 打包到 `ui/litellm-dashboard/out/` 目录
- `cp -r out/* ...` 将打包结果复制到 proxy 服务的 UI 静态文件目录
- `rm -rf /tmp/litellm_ui` 清除 UI 缓存，否则 LiteLLM 会使用旧的缓存文件

### 9. 本地启动服务验证

```bash
poetry run litellm --config ../guru-litellm/configs/proxy_config_local.yaml --debug --detailed_debug
```

**为什么**: 启动本地服务验证新供应商是否正常工作，`--debug --detailed_debug` 可以查看详细日志便于排查问题。

## 常见问题

### 模型从数据库加载后不显示

检查 `LlmProviders` 枚举是否包含该供应商。

### 请求没有发送到正确的 API Base

1. 检查 `openai_compatible_endpoints` 列表是否包含该端点
2. 检查 `get_llm_provider_logic.py` 中的端点检测逻辑
3. 检查 transformation.py 中的 `_get_openai_compatible_provider_info` 方法

### UI 下拉菜单看不到供应商

1. 检查 `provider_create_fields.json` 是否添加了配置
2. 检查 `provider_info_helpers.tsx` 是否添加了枚举和映射
3. 重新构建 UI 并清除 `/tmp/litellm_ui` 缓存

### 创建模型时报 "Unsupported provider"

检查 credentials 创建时使用的 provider 名称是否与 `LlmProviders` 枚举值一致。

## 文件变更汇总

### 新建文件（3 个）

| 文件路径 | 说明 |
|---------|------|
| `litellm/llms/{provider_name}/__init__.py` | 模块初始化 |
| `litellm/llms/{provider_name}/chat/__init__.py` | chat 模块初始化，导出配置类 |
| `litellm/llms/{provider_name}/chat/transformation.py` | 供应商配置类，继承 OpenAIGPTConfig |

### 修改文件（7 个）

| 文件路径 | 修改内容 | 步骤 |
|---------|---------|------|
| `litellm/constants.py` | 添加到 `LITELLM_CHAT_PROVIDERS`、`openai_compatible_endpoints`、`openai_compatible_providers` | 1 |
| `litellm/types/utils.py` | 在 `LlmProviders` 枚举中添加供应商 | 2 |
| `litellm/__init__.py` | 导出配置类、添加 key 变量、models 集合、add_known_models 逻辑、models_by_provider 映射 | 4 |
| `litellm/litellm_core_utils/get_llm_provider_logic.py` | 添加端点检测、模型前缀检测、配置类调用 | 5 |
| `litellm/main.py` | 在 `completion` 函数中添加处理分支 | 6 |
| `litellm/proxy/public_endpoints/provider_create_fields.json` | 添加 UI 供应商配置 | 7 |
| `ui/litellm-dashboard/src/components/provider_info_helpers.tsx` | 在 `Providers` 枚举、`provider_map` 和 `providerLogoMap` 中添加供应商 | 7 |
