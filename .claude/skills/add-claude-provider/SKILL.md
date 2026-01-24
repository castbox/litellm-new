---
name: add-claude-provider
description: 添加 Anthropic 标准协议（/v1/messages API）的供应商
---

# Process

本文档描述如何在 LiteLLM 中添加一个使用 Anthropic 标准协议（`/v1/messages` API）的新供应商。

## 架构说明

LiteLLM 的 Anthropic Messages API 实现采用继承架构：

```
BaseAnthropicMessagesConfig (抽象基类)
    └── AnthropicMessagesConfig (标准 Anthropic 实现)
            ├── AmazonAnthropicClaudeMessagesConfig (Bedrock 实现)
            └── {YourProvider}MessagesConfig (新供应商实现)
```

**推荐做法**：继承 `AnthropicMessagesConfig` 而不是 `BaseAnthropicMessagesConfig`，这样可以复用大部分逻辑，只需覆盖必要的方法。

## 信息收集

在开始之前，请向用户确认以下信息：

1. **供应商名称**（小写下划线格式）
   - 例如：`my_provider`
   - 用于代码中的标识符

2. **供应商显示名称**
   - 例如：`My Provider`
   - 用于 UI 显示和枚举值

3. **API 完整地址**（包含路径）
   - 例如：`https://api.myprovider.com/v1/messages`
   - 供应商的完整 API 端点

4. **Logo 文件名**（如果有）
   - 例如：`my_provider.png`、`my_provider.svg`
   - 放在 `ui/litellm-dashboard/public/assets/logos/` 目录

## 前置条件

- 新供应商使用 Anthropic 兼容协议（请求/响应格式与 Anthropic Messages API 一致）
- 只需要 `api_base` 和 `api_key` 进行认证

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
└── messages/
    ├── __init__.py
    └── transformation.py
```

**文件: `litellm/llms/{provider_name}/__init__.py`**
```python
"""{ProviderDisplayName} provider implementation"""
```

**文件: `litellm/llms/{provider_name}/messages/__init__.py`**
```python
from .transformation import {ProviderName}MessagesConfig

__all__ = ["{ProviderName}MessagesConfig"]
```

**文件: `litellm/llms/{provider_name}/messages/transformation.py`**

```python
"""
{ProviderDisplayName} provider implementation for Anthropic /v1/messages API

参考实现: litellm/llms/bedrock/messages/invoke_transformations/anthropic_claude3_transformation.py
"""
from typing import Any, List, Optional, Tuple

from litellm.llms.anthropic.experimental_pass_through.messages.transformation import (
    AnthropicMessagesConfig,
)
from litellm.secret_managers.main import get_secret_str

# 默认 API 地址（包含完整路径）
DEFAULT_API_BASE = "https://api.your-provider.com/v1/messages"


class {ProviderName}MessagesConfig(AnthropicMessagesConfig):
    """
    {ProviderDisplayName} provider implementation for Anthropic /v1/messages API

    继承自 AnthropicMessagesConfig，自动复用：
    - get_supported_anthropic_messages_params: 支持的参数列表
    - transform_anthropic_messages_request: 请求转换
    - transform_anthropic_messages_response: 响应转换
    - get_async_streaming_response_iterator: 流式响应处理

    只需覆盖：
    - get_complete_url: 构建 API URL
    - validate_anthropic_messages_environment: 设置认证 headers

    支持的 deployment 配置参数（通过 litellm_params 传递）：
    - api_base: API 完整地址（包含路径）
    - api_key: API 密钥
    """

    def get_complete_url(
        self,
        api_base: Optional[str],
        api_key: Optional[str],
        model: str,
        optional_params: dict,
        litellm_params: dict,
        stream: Optional[bool] = None,
    ) -> str:
        """构建 API URL"""
        api_base = (
            api_base
            or litellm_params.get("api_base")
            or get_secret_str("{PROVIDER}_API_BASE")
            or DEFAULT_API_BASE
        )
        return api_base.rstrip("/")

    def validate_anthropic_messages_environment(
        self,
        headers: dict,
        model: str,
        messages: List[Any],
        optional_params: dict,
        litellm_params: dict,
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
    ) -> Tuple[dict, Optional[str]]:
        """设置认证 headers - 使用 Bearer Token"""
        if api_key is None:
            api_key = (
                litellm_params.get("api_key")
                or get_secret_str("{PROVIDER}_API_KEY")
            )

        if "Authorization" not in headers and api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        if "content-type" not in headers:
            headers["content-type"] = "application/json"

        return headers, api_base
```

**为什么**: 继承 `AnthropicMessagesConfig` 可以复用大部分逻辑，只需覆盖 URL 构建和认证方法。

**配置方式**：

参数可以通过两种方式配置（优先级从高到低）：
1. **Deployment 配置**（UI 界面）- 通过 `litellm_params` 传递
2. **环境变量** - 作为备选方案

| 参数 | Deployment 配置 | 环境变量 | 默认值 |
|-----|----------------|---------|--------|
| API Base | `api_base` | `{PROVIDER}_API_BASE` | 代码中定义（包含完整路径） |
| API Key | `api_key` | `{PROVIDER}_API_KEY` | - |

**注意**: `api_base` 应该包含完整的 API 路径，例如 `https://api.provider.com/v1/messages`。

### 2. 注册到 LlmProviders 枚举

**文件: `litellm/types/utils.py`**

在 `LlmProviders` 枚举中添加新供应商：

```python
class LlmProviders(str, Enum):
    # ... 其他供应商
    {PROVIDER_NAME} = "{provider_name}"
```

**为什么**: `LlmProviders` 枚举用于验证供应商名称的合法性。如果不添加，从数据库加载模型时会因为供应商验证失败而被过滤掉。

### 3. 在 ProviderConfigManager 中注册

**文件: `litellm/utils.py`**

需要在两个方法中添加供应商配置：

**3.1 在 `get_provider_chat_config` 方法中添加**（在 `ANTHROPIC` 分支后面）：

```python
elif litellm.LlmProviders.ANTHROPIC == provider:
    return litellm.AnthropicConfig()
elif litellm.LlmProviders.{PROVIDER_NAME} == provider:
    return litellm.AnthropicConfig()
```

**3.2 在 `get_provider_anthropic_messages_config` 方法中添加**（使用延迟导入）：

```python
elif litellm.LlmProviders.{PROVIDER_NAME} == provider:
    from litellm.llms.{provider_name}.messages.transformation import (
        {ProviderName}MessagesConfig,
    )
    return {ProviderName}MessagesConfig()
```

**为什么**:
- `get_provider_chat_config` 用于 completion API 的请求转换
- `get_provider_anthropic_messages_config` 用于 Anthropic Messages API 的请求转换

### 4. 添加 completion 处理逻辑

**文件: `litellm/main.py`**

在 `completion` 函数中添加供应商处理分支（在 `elif custom_llm_provider == "anthropic":` 分支后面添加）：

```python
elif custom_llm_provider == "{provider_name}":
    api_key = (
        api_key
        or litellm.api_key
        or get_secret("{PROVIDER}_API_KEY")
    )
    api_base = (
        api_base
        or litellm.api_base
        or get_secret("{PROVIDER}_API_BASE")
        or "{default_api_base}"  # 包含完整路径
    )

    # 使用 Bearer Token 认证
    if headers is None:
        headers = {}
    if api_key and "Authorization" not in headers:
        headers["Authorization"] = f"Bearer {api_key}"
        api_key = None  # 清空 api_key，避免再设置 x-api-key

    response = anthropic_chat_completions.completion(
        model=model,
        messages=messages,
        api_base=api_base,
        acompletion=acompletion,
        custom_prompt_dict=litellm.custom_prompt_dict,
        model_response=model_response,
        print_verbose=print_verbose,
        optional_params=optional_params,
        litellm_params=litellm_params,
        logger_fn=logger_fn,
        encoding=_get_encoding(),
        api_key=api_key,
        logging_obj=logging,
        headers=headers,
        timeout=timeout,
        client=client,
        custom_llm_provider=custom_llm_provider,
    )
    if optional_params.get("stream", False) or acompletion is True:
        ## LOGGING
        logging.post_call(
            input=messages,
            api_key=api_key,
            original_response=response,
        )
    response = response
```

**为什么**: 这是实际调用 API 的入口。使用 `anthropic_chat_completions.completion` 处理 Anthropic 兼容协议的请求。

**重要**: `api_path` 处理逻辑必须在 `main.py` 中实现，因为 `anthropic_chat_completions.completion` 直接使用传入的 `api_base`。如果不在这里拼接路径，请求只会发送到 base URL 而不包含 API 路径。

### 5. 导出配置类（可选）

**文件: `litellm/__init__.py`**

如果需要通过 `litellm.{ProviderName}MessagesConfig` 直接访问配置类：

```python
from .llms.{provider_name}.messages.transformation import {ProviderName}MessagesConfig
```

**注意**: 由于步骤 3 中使用了延迟导入，这一步是可选的。

### 6. 添加供应商检测逻辑（可选）

如果需要根据 API Base 或模型名称自动检测供应商：

**文件: `litellm/litellm_core_utils/get_llm_provider_logic.py`**

```python
# 根据 API Base 检测
if api_base and "{api_domain}" in api_base:
    custom_llm_provider = "{provider_name}"

# 或根据模型前缀检测
elif model.startswith("{provider_name}/"):
    custom_llm_provider = "{provider_name}"
```

### 7. 添加到常量配置（可选）

**文件: `litellm/constants.py`**

```python
LITELLM_CHAT_PROVIDERS = [
    # ... 其他供应商
    "{provider_name}",
]
```

### 8. 添加 UI 供应商配置

**重要：命名一致性要求**

`provider_create_fields.json` 中的 `provider` 字段必须与 `provider_info_helpers.tsx` 中 `provider_map` 的键名完全一致。否则 UI 会将 provider 名称转换为小写，导致 "Unsupported provider" 错误。

命名风格参考现有供应商（如 `DeerAPI_Gemini`）：
- 使用 PascalCase + 下划线分隔
- 例如：`DeerAPI_Claude`、`FunCloud_Claude`

**文件: `litellm/proxy/public_endpoints/provider_create_fields.json`**

```json
{
  "provider": "{ProviderKey}",
  "provider_display_name": "{ProviderDisplayName}",
  "litellm_provider": "{provider_name}",
  "credential_fields": [
    {
      "key": "api_base",
      "label": "API Base",
      "placeholder": "{default_api_base}",
      "tooltip": "API 完整地址（包含路径）",
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
  "default_model_placeholder": "claude-3-opus"
}
```

**文件: `ui/litellm-dashboard/src/components/provider_info_helpers.tsx`**

**注意**：以下三处的键名必须与 `provider_create_fields.json` 中的 `provider` 字段完全一致。

1. 在 `Providers` 枚举中添加：
```typescript
export enum Providers {
  // ... 其他供应商
  {ProviderKey} = "{ProviderDisplayName}",
}
```

2. 在 `provider_map` 中添加映射：
```typescript
export const provider_map: Record<string, string> = {
  // ... 其他映射
  {ProviderKey}: "{provider_name}",
}
```

3. 在 `providerLogoMap` 中添加 logo（如果有）：
```typescript
export const providerLogoMap: Record<string, string> = {
  // ... 其他 logo
  [Providers.{ProviderKey}]: `${asset_logos_folder}{logo_filename}`,
}
```

### 9. 重新构建 UI

```bash
cd ui/litellm-dashboard
npm run build
cp -r out/* ../../litellm/proxy/_experimental/out/
rm -rf /tmp/litellm_ui  # 清除 UI 缓存
```

### 10. 本地启动服务验证

```bash
poetry run litellm --config ../guru-litellm/configs/proxy_config_local.yaml --debug --detailed_debug
```

### 11. 项目打包和推送

```bash
export TAG=your-tag

# 构建镜像（linux/arm64）
docker build --platform=linux/arm64 -t 851725654066.dkr.ecr.us-east-1.amazonaws.com/saas-guru/litellm:$TAG .

# 登录 ECR（如未登录）
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 851725654066.dkr.ecr.us-east-1.amazonaws.com

# 推送到 ECR
docker push 851725654066.dkr.ecr.us-east-1.amazonaws.com/saas-guru/litellm:$TAG
```

## 使用示例

```python
import litellm

# 方式 1: 使用 litellm.anthropic.messages.acreate
response = await litellm.anthropic.messages.acreate(
    model="{provider_name}/claude-3-opus",
    messages=[{"role": "user", "content": "Hello"}],
    max_tokens=100,
    api_key="your-api-key",
    api_base="https://api.your-provider.com",
)

# 方式 2: 通过 completion
response = litellm.completion(
    model="{provider_name}/claude-3-opus",
    messages=[{"role": "user", "content": "Hello"}],
    api_key="your-api-key",
    api_base="https://api.your-provider.com",
)
```

## 常见问题

### 模型从数据库加载后不显示

检查 `LlmProviders` 枚举是否包含该供应商。

### Unmapped LLM provider 错误

检查 `litellm/main.py` 中是否添加了供应商的 completion 处理分支。

### Unsupported provider 错误（如 "Unsupported provider - deerapiclaude"）

这是因为 `provider_create_fields.json` 中的 `provider` 字段与 `provider_info_helpers.tsx` 中 `provider_map` 的键名不一致。当 UI 找不到匹配的映射时，会将 provider 名称转换为小写（如 `DeerapiClaude` → `deerapiclaude`），导致与 `LlmProviders` 枚举中的值（如 `deerapi_claude`）不匹配。

**解决方法**：确保以下三处的键名完全一致：
1. `provider_create_fields.json` 中的 `provider` 字段
2. `provider_info_helpers.tsx` 中 `Providers` 枚举的键名
3. `provider_info_helpers.tsx` 中 `provider_map` 的键名

### 请求没有发送到正确的 API Base

1. 检查 `api_base` 是否包含完整路径（如 `https://api.provider.com/v1/messages`）
2. 检查 transformation.py 中的 `get_complete_url` 方法
3. 检查 `main.py` 中的默认 `api_base` 是否正确

### UI 下拉菜单看不到供应商

1. 检查 `provider_create_fields.json` 是否添加了配置
2. 检查 `provider_info_helpers.tsx` 是否添加了枚举和映射
3. 重新构建 UI 并清除 `/tmp/litellm_ui` 缓存

### 流式响应不工作

继承 `AnthropicMessagesConfig` 后流式响应应该自动工作。如果不工作：
1. 检查供应商的流式响应格式是否与 Anthropic 标准一致
2. 如果格式不同，需要覆盖 `get_async_streaming_response_iterator` 方法

## 参考实现

- [AnthropicMessagesConfig](litellm/llms/anthropic/experimental_pass_through/messages/transformation.py) - **推荐继承此类**
- [AmazonAnthropicClaudeMessagesConfig](litellm/llms/bedrock/messages/invoke_transformations/anthropic_claude3_transformation.py) - Bedrock 实现参考
- [BaseAnthropicMessagesConfig](litellm/llms/base_llm/anthropic_messages/transformation.py) - 抽象基类

## 文件变更汇总

### 新建文件（3 个）

| 文件路径 | 说明 |
|---------|------|
| `litellm/llms/{provider_name}/__init__.py` | 模块初始化 |
| `litellm/llms/{provider_name}/messages/__init__.py` | messages 模块初始化 |
| `litellm/llms/{provider_name}/messages/transformation.py` | 供应商配置类，继承 AnthropicMessagesConfig |

### 修改文件

| 文件路径 | 修改内容 | 必需 |
|---------|---------|------|
| `litellm/types/utils.py` | 在 `LlmProviders` 枚举中添加供应商 | ✅ |
| `litellm/utils.py` | 在 `ProviderConfigManager` 中注册（延迟导入） | ✅ |
| `litellm/main.py` | 在 `completion` 函数中添加处理分支 | ✅ |
| `litellm/__init__.py` | 导出配置类 | 可选 |
| `litellm/litellm_core_utils/get_llm_provider_logic.py` | 添加供应商检测逻辑 | 可选 |
| `litellm/constants.py` | 添加到 `LITELLM_CHAT_PROVIDERS` | 可选 |
| `litellm/proxy/public_endpoints/provider_create_fields.json` | UI 供应商配置 | ✅ |
| `ui/litellm-dashboard/src/components/provider_info_helpers.tsx` | UI 枚举和映射 | ✅ |
