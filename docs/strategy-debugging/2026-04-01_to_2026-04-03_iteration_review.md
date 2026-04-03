# 2026-04-01 至 2026-04-03 迭代评审

## 范围

- `2026-04-01` 的提交 `dcdfde4ca`：`feat(routing): 添加 SLO-First 成本/延迟平衡自定义策略文档`
- `2026-04-03` 的提交 `21c299c03`：`test(routing): 添加流式响应读取超时回退测试`

## 本版本更新内容

### 1. 路由策略与发布材料

- 新增自定义路由策略实现：`litellm/router_strategy/cost_latency_balanced.py`
- 为自定义路由策略增加运行时生命周期支持：
  - `Router.set_custom_routing_strategy()` 现在会调用 `on_attach()`
  - `Router.discard()` 以及策略替换时现在会调用 `cleanup()`
- 新增路由文档与回测 / 发布计划：
  - `docs/my-website/docs/routing.md`
  - `docs/strategy-debugging/cost-latency-routing-backtest-plan.md`
- 新增 Router 单元测试，覆盖：
  - SLO 过滤
  - 降级模式
  - 按 model group 的路由模式
  - cooldown / recovery
  - 运行时配置刷新

### 2. 空响应校验与回退链路

- 新增 `validate_first_chat_completion_response()`，用于拦截空的 chat completion 输出
- 将该校验接入到：
  - `litellm/utils.py` 的非流式 post-call 处理
  - `litellm/litellm_core_utils/streaming_handler.py` 的流式最终响应组装
- 新增测试，覆盖：
  - 非流式空响应回退
  - 流式最终空响应
  - 仅 tool call 的响应
  - 仅 function call 的响应

### 3. Dashboard 用量展示改进

- 新增 `ui/litellm-dashboard/src/components/view_logs/usage_utils.ts`
- `RequestViewer` 和 `SessionView` 现在会从多个 metadata 路径读取缓存命中 token，而不再只依赖 `additional_usage_values.cache_read_input_tokens`
- 新增前端测试，覆盖标准字段和嵌套回退路径

### 4. 读取超时的流式回退处理

- `litellm/litellm_core_utils/streaming_handler.py` 现在会把流式 `httpx.TimeoutException` 映射为 `MidStreamFallbackError`
- 新增 `test_acompletion_streaming_iterator_falls_back_on_read_timeout`，覆盖读取超时触发回退后的收集逻辑

## Review Findings

### 1. 流式回退可能在已经发出 `stop` chunk 之后继续输出内容

- 证据：
  - `litellm/litellm_core_utils/streaming_handler.py` 会先返回合成出来的最终 `finish_reason` chunk，然后才校验组装后的完整响应是否为空。
  - 下一次拉取时，`litellm/router.py` 会捕获 `MidStreamFallbackError`，并继续产出 fallback chunks。
  - 本地复现结果为：`router_stream_chunks= [('stop', None), (None, 'fallback')]`
- 影响：
  - 客户端可能会先观察到流已经结束，随后又收到新的 fallback 内容。
  - 对于在 `finish_reason="stop"` 后立即停止消费的 SSE 客户端或 SDK，可能会截断 fallback 输出，或者把整个流视为异常格式。
  - `2026-04-03` 的 timeout 改动扩大了这个问题的影响面，因为读取超时现在也会进入同一条 fallback 路径。
- 建议：
  - 在发出终止 chunk 之前先校验最终组装结果，或者在已经发出终止 chunk 后禁止再进入 fallback。
  - 增加一个 router 层回归测试，明确断言：发出 `stop` chunk 后不应再继续输出 fallback 内容。

### 2. 合法的 `audio` / `reasoning_content` assistant 输出会被误判为空响应

- 证据：
  - `litellm/litellm_core_utils/model_response_utils.py` 当前只把 `content`、content blocks、`images`、`tool_calls` 和 `function_call` 视为有效输出。
  - `litellm/types/utils.py` 中的 assistant message 还支持 `audio` 和 `reasoning_content` 等合法字段。
  - 本地复现结果为：
    - `reasoning_only rejected: empty completion response`
    - `audio_only rejected: empty completion response`
- 影响：
  - 支持音频输出或推理输出的 provider 可能会被错误地触发 fallback，或者直接抛出 `APIResponseValidationError`。
  - 该问题会同时影响非流式 post-call 处理和流式最终响应校验。
- 建议：
  - 将 `audio`、`reasoning_content`，以及可能的 `thinking_blocks` 一并视为非空 assistant 输出。
  - 补充这些响应形态的兼容性测试。

## 建议重点测试范围

### A. 路由策略行为

- `balanced` 模式下，当多个候选都满足 SLO 时，是否正确选择更低成本的 deployment
- `balanced` 模式下，当 SLO 不满足时，是否正确退化到更偏向延迟 / 负载的选择
- `cost-first` 和 `latency-first` 的 per-model-group override 是否按配置生效
- 运行时调用 `update_routing_config()` 后，权重和模式是否刷新，同时不丢失缓存状态
- 异常 timeout / 5xx 窗口下的 cooldown 与 recovery reset 逻辑是否正确
- 调试 metadata 字段（`_selected_reason`、`_resolved_routing_mode`、`_score_breakdown`、`_slo_pass_set`）是否稳定

### B. 流式回退与 timeout 行为

- 空流式响应是否会在发出终止 `stop` chunk 之前就触发 fallback
- 首个 chunk 之前发生 timeout 时，是否能正确回退
- 已产生部分内容后发生 timeout 时，是否能基于已有内容继续回退
- 在最终 `stop` 之后发生 timeout / fallback 时，是否不会再追加额外内容
- 主流已输出部分 chunks 时，fallback 流的 usage 合并是否仍然正确

### C. 响应校验兼容性

- 非流式空白字符串响应是否仍会触发 fallback
- 仅 tool call 的响应是否仍视为合法
- 仅 function call 的响应是否仍视为合法
- 仅 image 的响应是否仍视为合法
- 仅 reasoning 的响应是否应视为合法
- 仅 audio 的响应是否应视为合法

### D. Dashboard 用量展示

- 当标准字段 `cache_read_input_tokens` 存在时，是否仍优先使用该字段
- 是否能正确回退到 `additional_usage_values.prompt_tokens_details.cached_tokens`
- 是否能正确回退到 `usage_object.prompt_tokens_details.cached_tokens`
- Session 级别的缓存 token 汇总是否与单行展示一致

## 验证执行情况

### 已通过

- `python3 -m pytest tests/router_unit_tests/test_cost_latency_balanced_routing.py`
- `python3 -m pytest tests/test_litellm/test_post_call_processing.py tests/test_litellm/test_router_empty_response_fallback.py`
- `python3 -m pytest tests/test_litellm/litellm_core_utils/test_streaming_handler.py -k 'empty_final_response or late_text'`

### 部分验证 / 尚未完整验证

- `python3 -m pytest tests/test_litellm/test_router.py -k 'streaming_iterator or async_function_with_fallbacks_common_utils'`
  - 当前本地环境里只真正执行了 sync 测试
  - async 测试因为本地 pytest 环境缺少预期的 async plugin / 配置支持而被跳过
- 这次评审没有运行前端 `vitest` 测试

## 可用于版本更新说明的摘要

- 新增 SLO-first 成本 / 延迟平衡路由策略，以及对应的生命周期钩子、回测文档和发布建议
- 为非流式与流式链路新增空 chat-completion 响应校验
- 优化 Dashboard 中 cache read token 的展示逻辑，支持多种 metadata 回退路径
- 新增流式读取超时触发 fallback 的处理逻辑和回归测试覆盖
