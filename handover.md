# LiteLLM v1.106.4 定制升级交接

本分支将线上 20260525 的定制能力迁入官方 v1.106.4，当前交付范围为代码、本地回归、隔离数据库演练和本地 linux/arm64 候选镜像

| 对象 | 固定版本 |
| --- | --- |
| 原官方基线 | v1.82.3-stable，`61409275c8d8478d0a7ffc23d375a4fd86717b23` |
| 线上定制源码 | `9e104f270e1dc9dee6c96398b4109e0eba120f20` |
| 线上镜像 | `851725654066.dkr.ecr.us-east-1.amazonaws.com/saas-guru/litellm:20260525` |
| 线上镜像 index digest | `sha256:6d693623cc6bcded25125672c9e4923c2a0ee99868def5efc1a42583e630d142` |
| 新官方基线 | v1.106.4，`ea7ca16dbc3904d9e59a9505f379a2ca3091821f` |
| 开发分支 | `codex/upgrade-v1.106.4` |

48 个历史核对编号逐项记录于[迁移去向台账](upgrade-v1.106.4-traceability.md)，其中 38 项保留、适配或沿用新版实现，10 项按已确认范围排除

标签路由重试 T01 的旧定制补丁不迁移，使用目标版本官方已有机制，不安排该旧补丁的专项验收。R01 至 R09 的成本与延迟平衡策略及其专用参数、界面、实例管理和日志均不迁移。旧线上镜像已经包含该策略代码，但线上调度未选中，不能写成“未部署”

## 业务继续使用的能力

保留 17 个接入标识及原有环境变量别名，涵盖 11 个 OpenAI 兼容接入、azure_openai_v1、两个 Gemini 接入、两个 Claude 接入和 ApiGo。`ominilink_gemini` 是历史兼容拼写，配置中继续保留。Azure v1 使用配置的完整 v1 base，Claude 自定义接入使用各自完整路径和 Bearer 认证

ApiGo 继续通过 JSON 注册 Chat Completions 和 Responses。历史 `apigo/gpt-4o` 元数据中输入、输出价格为 0，仅表示配置值。新版官方内置价格表不再覆盖全部旧 OpenRouter 价格条目，实际使用的部署需要核对自定义价格、缓存价格及服务层级价格

普通回答和流式回答均检查完整结果是否有效。工具调用、图片、音频、推理、拒绝回答和新版 Claude 的有效压缩摘要允许没有普通文本；空结果进入失败处理，有常规备用配置时直接转备用。流式检查使用分段副本，避免日志拼接改动调用方已收到的工具参数。已经发送的内容无法撤回，部分输出后的业务拼接和计费仍需在发布演练中验收

六类每日支出继续按对外模型名 `model_group` 区分。这是把已有字段加入队列键、批量合并键和唯一索引，没有新增该字段。缺失值在新写入时归一为空字符串，历史 NULL 和已合并记录不会自动回填或拆分

后台新增模型时过滤空 `vector_store_ids`。编辑时沿用新版区分“未配置”和“主动清空”的行为，清空已有向量库会提交空列表。模型列表显示允许公开的模型组别名，并保留新版的权限、搜索、分页和隐藏规则。模型组别名是给同一组后端部署增加业务调用名称，不是重命名单个部署

健康检查沿用新版按模式配置额度的方式。需要保留旧版 32 token 检查额度时，在部署的 `model_info` 中明确设置 `health_check_max_tokens: 32`，不全局覆盖新版对非聊天端点的保护

## 本地开发与构建

Python 使用官方锁定的 3.13 环境，前端使用 `.nvmrc` 对应的 Node 24 版本。升级分支保留官方 uv workspace、Rust 扩展、LiteAdmin 和独立 UI 构建阶段。默认配色 UI 由 ui-builder 阶段构建；存在 enterprise_colors 时再执行对应构建脚本

```sh
uv sync --frozen --extra proxy --extra extra_proxy --python 3.13
LITELLM_LOCAL_MODEL_COST_MAP=True PYTHONPATH=. uv run --no-sync pytest -q tests/unit/test_main_custom_providers.py
BASE_REF=ea7ca16dbc3904d9e59a9505f379a2ca3091821f make check
docker build --platform linux/arm64 --progress plain -t litellm-upgrade:v1.106.4-candidate .
```

当前远端默认分支仍包含旧定制版本，检查本次迁移新增问题时，将静态检查比较基线固定为上述新官方 SHA。没有修改检查预算、ANY_CAPS 或门槛。`make check` 的日志位置会打印到命令输出，可据此复核结果

受影响后端组合通过 1363 项，后续渠道密钥隔离回归通过 94 项，完整 Anthropic Chat 转换及响应检查通过 474 项；这些测试集合有重叠。前端四个指定文件通过 222 项，另有 4 项官方预期失败。最终 `make check` 通过，源码类型检查满足官方存量规则门槛，e2e 类型检查为零错误，前端有 24 项存量 lint 警告。验证边界和逐项证据见迁移去向台账

新增接入优先沿用 `litellm/llms/openai_like/providers.json` 的注册机制；协议有差异时参考本分支 Gemini 和 Claude 配置。修改后需要同时核对供应商识别、参数映射、公开配置、凭证字段、UI、普通与流式调用、价格来源及对应单测。ApiGo 的接入示例为 `apigo/<上游模型名>`，显式提供 `api_base` 和 `api_key` 可覆盖默认配置；公开 endpoint 元数据保留其历史文档地址，该地址不代表本分支已向官方发布文档

旧 `.claude/settings.local.json` 是工具本地权限，不复制到升级代码。旧三份协议接入指南由上述新版接入说明和当前实现替代。旧价格 CSV 留在固定线上提交中追溯，不作为运行时价格配置。旧前端生成文件全部由新版定制源码重新构建

## 数据库与发布边界

数据库操作以[迁移操作说明](litellm-proxy-extras/upgrade-v1.106.4-runbook.md)为准。旧版启动存在强制对齐旧 schema 的恢复逻辑，升级期间和回退期间必须防止它改回旧结构。共库上线前，两版应用实例都应有效禁止自动 DDL，使用单一迁移任务，并完成生产副本上的旧、新版共库读写与重启演练

本地演练使用 PostgreSQL 17、旧定制 schema 和合成的历史迁移记录及支出、MCP 审核测试数据，不能等同于生产库副本。真实供应商连通、启用的日志回调、生产规模锁影响、共库滚动升级、回退和版本安全准入仍是发布阶段的验收内容。本次未部署到生产、未推送 ECR 镜像、未操作生产数据库
