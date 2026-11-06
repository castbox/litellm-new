# Router 流式调用链审查

审查基线为 `77e8dfaa43`，复核此前的修复提交 `6727d57768`。范围是 Chat Completions 的同步、异步 SDK 和 Router 路径，包括建流、错误映射、失败回调、冷却、重试、order 切换及流消费

## 结论与修正

此前把 `fetch_stream()` 加入 `main.acompletion()`，能让异步 Vertex 建流错误进入 SDK 失败处理，但留下了 Router 的建流逻辑，也遗漏了同步 Vertex 路径

本次把 HTTP 建流统一放回 provider 适配器。Vertex 的同步和异步实现，以及存在同类延迟建流的 Codestral、Predibase 异步实现，均在返回 `CustomStreamWrapper` 前完成 HTTP 请求和状态校验。Router 的同步、异步建流代码和此前在 `main.py` 增加的调用全部移除

同时确认 Vertex 的 `timeout` 参数没有传给建流 HTTP 请求。配置 `stream_timeout=5/8` 的请求在测试中实际使用共享客户端的 `read=6000`。本次在 Vertex 同步、异步和 Codestral 异步建流时传递已解析的 timeout；Predibase 已经传递该参数

## 执行链与职责

| 阶段 | 实现位置 | 职责 |
| --- | --- | --- |
| 请求入口 | `Router.acompletion()` / `Router.completion()` | 记录请求上下文，进入重试和 fallback 调度 |
| 尝试调度 | `async_function_with_retries()` / `function_with_retries()` | 解析重试预算，发起下一次尝试 |
| 选择 deployment | `async_get_available_deployment()` / `get_available_deployment()` | 应用访问、健康、冷却、order 和路由策略过滤 |
| 调用前检查 | `Router._acompletion()` / `_completion()` | 准备参数和客户端，执行调用前检查；异步路径管理并发槽 |
| HTTP 建流 | provider 适配器 | 复用客户端，传递 timeout，校验 HTTP 状态，返回可消费的流 |
| SDK 异常处理 | `main.py`、`utils.client` | 把 provider 错误映射为标准异常，执行失败 hook 和回调 |
| 冷却 | `deployment_callback_on_failure()`、`CooldownCache` | 根据 deployment 配置、响应头和全局设置写入冷却 |
| Router 错误处理 | `_acompletion()` / `_completion()` 的异常分支 | 记录失败 deployment 和重试配置，将异常交给调度层 |
| 流消费 | `CustomStreamWrapper`、Router streaming iterator | 处理 chunk、usage、完整响应校验及消费阶段错误 |

建流错误发生在 SDK 调用尚未返回时。SDK 的 `utils.client` 异步异常分支先直接执行同步 `failure_handler`，再等待异步失败回调；负责写冷却的 Router 同步回调因此先于重试完成。没有新增独立的冷却逻辑或重试循环

成功建流只等待 HTTP 状态和响应头。响应正文由调用方开始迭代后读取。同步 Vertex 适配器还显式初始化 provider iterator，避免把依赖 `__iter__()` 初始化状态的对象直接交给 wrapper 的 `next()`

缓存回放使用已经构造好的 iterator。MCP 包装器有自己的迭代入口。本次保留 `CustomStreamWrapper.fetch_stream()` / `fetch_sync_stream()` 作为直接使用 wrapper 时的兼容接口，Router 和标准 provider 调用链不再依赖它们发起 HTTP

## 重试与 order 的实际语义

deployment 的 `max_retries` 传入模型调用层。Router 的 `num_retries` 决定外层重新尝试次数；初次失败后，当前实现依次考虑请求值、失败 deployment 的配置、Router 默认值，并处理显式 retry policy 的覆盖

`metadata.max_retries` 是 Router 写入的重试预算日志字段，不能据此推断模型客户端的 `max_retries` 设置

`num_retries` 没有天然绑定同一 order。普通重试重新执行 deployment 选择；过滤冷却目标后，默认取最低的可用 order，因此一次重试可以进入更高 order。order fallback 另外通过 `_target_order` 指定目标层级。重试循环已建立的预算也不会因为后续选中了另一个 deployment 就自动重新开始计算

本次保留这套语义。两条同步、异步 HTTP 回归都验证：两个 order=5 目标各返回一次 429，分别写入 15 秒冷却，随后由 order=10 返回成功；紧接着的请求避开两个冷却目标

## 仍需明确的边界

冷却记录不会撤回已经发往上游的请求。deployment 选中之后还会执行异步上下文压缩、调用前检查和 SDK 认证等步骤，当前在真正发起 HTTP 前没有第二次冷却检查。选中目标后暂停在这些异步步骤的请求，仍可能在另一个请求写入冷却后发出

当前分支的 `MaxParallelRequestsLimit` 在并发槽满时直接返回本地 429，不会等待空闲槽。因此上述窗口不能解释成“排队等待 semaphore 的请求”，也不应通过新增排队机制来修补

跨 worker 的冷却读取有默认 1 秒缓存间隔。写入 Redis 和其他 worker 观察到新状态之间存在窗口。本次修复不能作为“429 后所有 Pod 立即停止该 deployment 的全部请求”的证明

HTTP 建流成功之后的正文读取失败，走 `CustomStreamWrapper` 的消费阶段错误处理；其中失败回调由任务调度，和 SDK 建流失败时先完成同步冷却的顺序不同。Router 对已经输出内容的流也限制自动切换，避免拼接两个模型的答案

`stream_timeout` 最终传到 HTTP 客户端后约束网络操作，包括读取等待；它不是模型组的总耗时预算，也不是固定的整个生成时长上限。多次尝试的累计时长及连接、认证等阶段仍需分别考虑

`success_calls` 和 Router 的 `200 OK` 日志出现在建流成功之后、完整正文校验之前，不能单独证明最终有有效输出

同步失败回调包含冷却存储和日志处理，高错误率下有执行成本。正常路径复用原客户端并只发起一次 HTTP 请求；没有新增后台请求或把完整流收集后再返回。实际吞吐变化仍需要候选镜像压测

## 验证

新增或替换的 HTTP 边界回归覆盖同步、异步 Vertex 的 400/429/503 映射，两个 order=5 目标的冷却与后续路由，响应头保留，以及 Codestral、Predibase 建流错误

成功流测试使用在 SDK 返回前禁止读取的 HTTP body，验证不会提前消费正文，并检查请求总数为一次。Router 测试读取实际 HTTP request 的 timeout extensions，确认三次尝试分别使用 5、5、8 秒的 read timeout

把源码临时还原为 `77e8dfaa43` 后，14 个相关回归全部失败；恢复修复后全部通过。另一个空图片响应测试也在原始基线上失败，和此前确认的 4 个空文本响应测试一起作为已有失败单独记录

最终扩大回归为 2,149 项通过，覆盖 SDK、Router、streaming handler、cooldown cache/handler、Vertex Gemini、Predibase 和 Codestral 相关测试。没有使用真实 provider 凭证或付费调用

扩大回归排除了已经在原始基线上复现的 5 项空响应失败：`test_completion_missing_role`、`test_completion_strips_eager_input_streaming_before_openai`、`test_custom_provider_with_extra_headers`、`test_custom_provider_with_extra_body`，以及 Vertex `test_litellm_api_base[image_generation-vertex_ai]`。排除这些既有失败不代表全仓测试通过

使用 `BASE_REF=77e8dfaa436259cc9ffb550e62e837b86cfe7b3e make check`，相对线上源码基线的完整门禁通过，包括 Ruff、格式、type discipline、test quality、basedpyright 增量检查和循环导入检查。这不代表整条升级分支相对默认分支的已有门禁问题已经解决

本次没有构建或发布镜像，没有修改线上配置，也没有执行生产压测。以上证据证明本地 HTTP 边界行为和相关回归结果，尚不构成生产吞吐、跨 Pod 冷却传播或最终请求成功率的实测结论
