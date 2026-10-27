# 20260525 定制改动迁往 v1.106.4 的逐项台账

本表保留原全量差异附录的 48 个编号，一行对应一个历史核对条目，不能解释为 48 项互相独立的业务功能。旧官方、线上定制、新官方的固定 SHA 和镜像 digest 见[交接说明](handover.md)

38 项保留、适配或沿用目标实现，10 项按已确认的升级范围排除。表中验证描述的是本地代码回归，不代表生产启用状态。已知线上成本与延迟平衡策略的代码已部署，但调度未选中；其他能力未逐项确认线上使用情况

## 渠道接入与管理

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| P01 | 11 个 OpenAI 协议接入 | 迁移 `litellm/llms/{deerapi,infiniai,bltcy,xiakexing,shubiaobiao,omnilink,onerouter,funcloud,comflychat,apimart,toapis}`，接入 ProviderConfigManager、模型识别及价格元数据 | `tests/unit/test_main_custom_providers.py`，同步、异步、普通、流式请求以及旧环境变量 key 别名 |
| P02 | Azure OpenAI v1 | 适配 `litellm/llms/azure_openai_v1/chat/transformation.py`，保留 v1 base、旧密钥回退和标识 | `tests/unit/llms/azure_openai_v1` 及 17 渠道协议回归 |
| P03 | 两个 Gemini 标识 | 迁移 `deerapi_gemini`、`ominilink_gemini`，使用新版 Gemini 分派和参数映射，保留独立 base/key 和自定义计费，缺少自定义密钥时不借用标准 Gemini 密钥 | `tests/unit/test_main_custom_providers.py`、`tests/unit/llms/deerapi_gemini`，含缓存价格 |
| P04 | 两个 Claude Messages 标识 | 迁移 `deerapi_claude`、`funcloud_claude` 配置和注册，支持 Chat 调用及新版原生 Messages 路径 | 17 渠道 Chat 四种组合、两个 Claude 的异步原生 Messages 普通和流式请求；官方原生 Messages 同步入口未实现，不额外新增 |
| P05 | ApiGo 注册与价格 | 迁移 `litellm/llms/openai_like/providers.json`、两份 endpoint 元数据及两份价格表；保留 Chat、Responses 和历史零价配置值 | `tests/unit/llms/openai_like/test_apigo_provider.py`、`tests/unit/test_main_custom_providers.py`、公开 endpoint TestClient 回归 |
| P06 | 注册及后台入口 | 适配 `constants.py`、`__init__.py`、`_lazy_imports_registry.py`、`provider_create_fields.json`、UI provider map 和 11 张 Logo | 供应商识别、环境变量、公开配置、`provider_info_helpers.test.tsx`、新增模型表单及最终 UI 构建 |

## 已确认不迁移的路由定制

| 编号 | 历史能力 | 本次去向 |
| --- | --- | --- |
| T01 | 标签路由重试旧补丁 | 不迁移旧补丁，使用目标版本官方已有机制，不安排该旧补丁专项验收 |
| R01 | balanced、cost-first、latency-first 模式 | 不迁移新增策略及三种专用模式 |
| R02 | 延迟和可靠性门槛 | 不迁移专用门槛及降级集合 |
| R03 | 成本、延迟、负载综合评分 | 不迁移专用评分和指标计算 |
| R04 | 策略内 RPM、TPM 过滤 | 不迁移该策略的配套限额逻辑，官方其他路由能力沿用目标版本 |
| R05 | 冷启动和恢复采样 | 不迁移专用采样、种子和恢复机制 |
| R06 | 有条件随机探索 | 不迁移 epsilon 探索和成本倍率约束 |
| R07 | 异常窗口和冷却联动 | 不迁移专用异常窗口、触发和指标存储 |
| R08 | 专用配置、界面及实例生命周期 | 不迁移策略参数面板、custom 配置读写、回调注册和清理 |
| R09 | 专用选择原因日志 | 不迁移策略候选评分、原因及相关日志元数据 |

## 响应检查和回退

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| E01 | 聊天完整结果有效性 | 迁移 `model_response_utils.py` 和 `utils.post_call_processing`，检查首 choice，接受文本、工具、音频、图片、推理、refusal 及新版有效 compaction 摘要 | `test_model_response_utils.py`、`test_utils_post_call_processing.py`，空结果失败及有效非文本结果 |
| E02 | 图片和 Responses 有效性 | 迁移 `validate_image_generation_response`、`validate_responses_api_response`；Responses 非 completed 状态保留 | `test_utils_post_call_processing.py`，空图片、空 completed 结果拒绝及图片输出接受 |
| E03 | 流式结束、日志和缓存顺序 | 适配 `streaming_handler.py`：复制分段后拼接，在结束块和自然结束时验证；无效结果进入失败记录，保留已知用量；同步调用继续逐段通知日志回调，完整响应通过校验后才记录最终成功 | `test_streaming_handler.py`，同步/异步、有/无 finish 的空流、工具参数分段保持、usage-only、拼接失败用量及新版收尾回归；`test_sync_stream_notifies_each_chunk_before_logging_validated_success` 的 8 个组合验证逐段回调、最终成功次数和日志开关 |
| E04 | 备用模型及异常 | 适配 `router.py` 和新版 stream fallback：校验失败且有普通备用时跳过相同部署的普通重试，保留官方中途异常与部分用量处理 | `test_router.py::test_empty_response_uses_backup_without_retrying_the_same_deployment`，真实 Router 加 HTTP 传输替身验证主备各调用一次；流式异常回归 |

## 用量与费用记录

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| U01 | 保存只有 usage 的分段 | 沿用新版 `CustomStreamWrapper` 对 usage-only 的保存和最终汇总 | `test_streaming_handler.py` 中 usage-only、有无 stream_options、finish 后 usage 回归 |
| U02 | 空输入明细不覆盖非空明细 | 沿用新版 `ChunkProcessor` 非空保留及 cache TTL 明细处理 | `test_streaming_chunk_builder_utils.py`、`test_streaming_handler.py` 的多段明细保留与 TTL 回归 |
| U03 | 完整 Usage 字段与 0 值 | 适配两个用量汇总入口：累计汇总保留额外非 None 字段和 0，拼接器支持字典和 BaseModel 明细，保留新版 text/image 字段及对象型 cost | `test_calculate_total_usage_keeps_extra_fields_and_zero_values`、完整拼接器回归和 Perplexity cost 用例 |
| U04 | 缓存字段归一化和入库 | 适配 `spend_tracking_utils.py`、`streaming_chunk_builder_utils.py`，从 cached_tokens 补顶层缓存读用量，沿用新版数据库两种缓存字段读取 | 支出归一化、数据库 writer、缓存计价和缓存 TTL 回归 |
| U05 | 标准日志补取 usage | 迁移标准日志 `metadata.usage_object` 的副本作为缺失响应用量的回退，保留新版非推理调用不计费规则 | `test_spend_tracking_utils.py`，缓存读写、0 值、输入对象不改动及管理调用回归 |
| U06 | Chat 和 Responses 混合用量 | 迁移 `ResponseAPILoggingUtils.is_response_api_usage` 的 Chat 字段优先规则 | `test_responses_utils.py::TestResponseAPILoggingUtils::test_chat_usage_with_responses_aliases_keeps_chat_counts_and_details`，核对最终计数、缓存明细和额外字段 |
| U07 | OpenRouter 默认索取用量 | 适配到 `litellm/llms/openrouter/chat/transformation.py`，仅未显式传 stream_options 时加入 include_usage | `test_openrouter_chat_transformation.py`，未设置、空对象、显式 true/false 四种情况 |

## 协议和图片兼容

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| C01 | OpenRouter 模型名称解析 | 沿用新版 `get_llm_provider_logic.py` 的原生名、外层前缀和显式供应商解析 | `tests/unit/llms/openrouter/test_openrouter_provider_routing.py` |
| C02 | Gemini HTTPS 图片 | 迁移到新版 Gemini 同步转换和异步预取规则，仅图片 MIME 下载并 inline；Files API、非图片 URI 保留新版路径 | `test_transformation.py`，同步/异步图片、非图片透传、Files API 和下载失败 |
| C03 | FunCloud Claude 图片 | 适配 `prompt_templates/factory.py` 和 `FuncloudClaudeMessagesConfig`，Chat、原生 Messages 都转换图片 URL；Messages 使用副本 | 两个 Claude 映射测试文件，以 HTTP 图片数据检查 Base64 内容、原请求不变和下载失败 |
| C04 | Claude 认证和供应商保留 | 适配 Chat handler、转换层和原生 Messages，使用对应 Bearer，流 wrapper 保留自定义 Claude 标识 | 17 渠道协议回归的 headers、URL、同步/异步流标识，以及原生 Messages 调用 |

## 数据库和统计

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| D01 | 六类支出按对外名称区分 | 适配 `daily_spend_bulk_upsert.py` 和 writer，队列去重、排序、批量合并及 SQL 冲突键都带 model_group，同时保留 endpoint 和 MCP 维度 | 两个映射单测文件及 `tests/integration/spend/test_daily_spend_model_group.py` 的六类真实 PostgreSQL 并发回归 |
| D02 | 配套 schema 和每日迁移 | 三份 schema 同步，新迁移 `20261027000000_preserve_daily_spend_model_group`，已有正确索引保留，不改历史行 | 官方索引、定制索引、并存三种状态，重复执行、历史 NULL、完整旧迁移 ledger 演练和三份 schema diff |
| D03 | MCP 审核字段一致 | 沿用新版字段和官方恢复迁移，不重新执行会覆盖历史的旧 schema_sync 和旧恢复脚本 | 从旧 schema 重放全部待执行迁移，核对 MCP 审核测试数据、旧 checksum 和最终 schema 一致 |
| D04 | AI 用量问答摘要 | 适配 `ai_usage_chat.py`，保留请求成功/失败和 token 汇总、对外名和底层名区分、失败排行及解释边界 | `test_ai_usage_chat.py`，跨日累计、成功/失败、token 汇总和失败排序 |

## 管理和健康检查

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| A01 | 健康检查额度 | 使用新版 `model_info.health_check_max_tokens` 显式配置 32 的需求，保留按模式判断和推理、通配符配置，不恢复旧全局强制默认 | `test_health_check_max_tokens.py`、`test_health_check_functions.py`，配置方式见交接说明 |
| A02 | moderation 模式 | 迁移后台模式选项、类型和 moderation/moderations 健康检查分派 | `test_health_check_helpers.py`、新增模型表单和 UI 构建 |
| A03 | 详情按部署 ID 测连接 | 沿用新版 `model_info_view.tsx` 的指定部署测试和错误显示 | `model_info_view.test.tsx` |
| A04 | 空向量库字段 | 新增时过滤空列表，编辑沿用新版语义：未配置不提交，主动清空已有值则提交空列表 | `handle_add_model_submit.test.tsx` 两类新增 payload，`model_info_view.test.tsx` 清空已有配置 |
| A05 | 模型列表显示可见别名 | 在新版 v2 列表使用 Router 完整模型列表，保留权限、搜索、分页、隐藏和部署归属处理 | `test_routes_model_info.py::test_v2_model_info_keeps_visible_aliases_search_pagination_and_ownership` 的六种情况 |
| A06 | 无数据库加载本地路由配置 | 沿用新版 ProxyConfig 加载路径；不携带 R08 的专用策略清理和重载逻辑 | 本地 Proxy 按 YAML 启动，无 DATABASE_URL，核对 router_settings、业务别名和请求分派 |

## 构建、产物和资料

| 编号 | 能力 | 去向与新版实现 | 对应验证 |
| --- | --- | --- | --- |
| B01 | 默认配色也构建 UI | 沿用官方 ui-builder 始终编译默认 UI；存在 enterprise_colors 时由 build_admin_ui 调用配色构建 | 默认配色完整构建和镜像 UI 检查；review 在补齐 curl 的 builder 中挂载最终 build_ui.sh，使用仓库配色样例，完成 Node 首次安装、npm ci、类型检查、静态页面导出及 Proxy 输出目录检查 |
| B02 | Node 和前端依赖准备 | 按新版 `.nvmrc` 使用 Node 24；本地脚本准备版本、核对依赖并按 lock 选择 npm ci，固定 nvm 下载及校验和；builder 补齐 curl，加载 nvm 时禁用自动切换，再明确安装所需版本，避免首次安装提前退出 | npm ci、前端类型检查和静态构建；补修后 Node 首次安装及完整企业构建路径验证通过，见 B01 |
| B03 | apk 安装重试 | 迁移 `docker/apk_add_with_retry.sh`，四个 Wolfi stage 使用；默认 5 次、间隔 10 秒，最终失败退出 | shell 首次成功、第三次成功、耗尽失败、非法次数，以及候选镜像构建 |
| B04 | 本地扩展包入镜像 | 沿用官方 uv workspace 安装本地 extras，三份 schema、迁移和生成 Prisma 客户端配套 | 隔离库迁移、最终镜像中的安装包 schema、迁移与客户端核对 |
| B05 | 前端生成产物 | 从新版定制源码重建 UI，不复制旧版 672 个变化的生成文件 | 静态构建成功、镜像 UI 页面及引用的 _next 资源检查 |
| B06 | 指南和参考资料 | 新增本交接说明、此台账及迁移操作说明；旧协议指南由当前实现和新版说明替代，工具权限文件不复制，价格 CSV 仅留 Git 历史 | 原资料去向见交接说明；ApiGo 历史价格与公开入口分别核对 |
| B07 | 回归及环境适配 | 按新版映射测试位置迁移旧问题，补 HTTP 协议、流式和数据库并发回归；排除 .venv-typecheck 本地目录进入镜像上下文 | 受影响后端和前端测试、四个静态检查 gate、前端 API 类型漂移检查、迁移不重写数据检查 |

## 证据如何复核

源码位置均相对于仓库根目录。旧 23 个提交、822 个文件和 48 个历史条目的关联继续以固定线上提交及[原全量差异核对附录](https://chatgpt.com/space/page_278b47a8ceac8191a5789a48583b7821)追溯。本表记录它们在新版本中的去向，没有把官方新增代码全算成旧补丁迁移

2026-10-27 本地验证结果：受影响后端组合通过 1363 项；随后补充的渠道密钥隔离场景与既有供应商场景合跑通过 94 项，其中新增 4 个隔离场景。新版 Claude 压缩摘要兼容修复后，完整 Anthropic Chat 转换及响应有效性测试通过 474 项，其中新增 3 个摘要有效性场景。这几组回归有重叠，不能相加作为独立测试总数。前端四个指定文件通过 222 项，另有 4 项官方 expected fail，前端类型无错误

最终 `make check` 比较固定新官方 SHA 通过。四个 gate 均满足原有规则计数门槛，未修改门槛；源码类型检查通过不表示源码零类型错误，e2e 及 harness 类型检查为 0 errors、0 warnings。前端 lint 有 24 项存量警告，0 errors，OpenAPI 与前端生成类型无漂移

Review 补修后，同步流式、日志、分段拼接、自定义回调和渠道调用的相关后端组合通过 872 项；新增逐段日志回调测试的 8 个参数组合在最终测试版本上单独复跑通过。固定新官方 SHA 的 `make check` 再次通过。这些回归集合与上述历史测试有重叠，不累加为独立总数

迁移数据库测试使用 `DATABASE_URL` 指向隔离 PostgreSQL，并只在随机 schema 内操作。完整 ledger 演练是合成历史环境，不是生产数据副本。供应商测试使用 HTTP 传输替身验证实际分派与序列化，本地镜像冒烟使用脚本上游，均不能替代真实供应商验收

复核命令及发布边界见[交接说明](handover.md)和[迁移操作说明](litellm-proxy-extras/upgrade-v1.106.4-runbook.md)。本地验证数量和最终镜像标识随本分支交付结果记录，生产上线需要单独完成升级概要设计中的发布验收
