# 将 v1.82.3-stable 整合到 routing-strategy 的实施计划

> **给执行型 agent 的说明：** 必须使用子技能 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans`，按任务逐项实现本计划。步骤使用复选框语法（`- [ ]`）进行跟踪。

**目标：** 将 `/Users/wenyu/Documents/code/litellm` 中的 `v1.82.3-stable` 作为新上游基线整合进 `/Users/wenyu/Documents/code/litellm-new` 的 `routing-strategy` 体系，同时保留当前分支的自定义 provider、stream timeout 修复，以及成本/延迟平衡路由能力。

**架构：** 不建议把 `v1.82.3-stable` 直接 merge 进旧的 `routing-strategy`。更稳妥的路径是：先在 `litellm-new` 中引入 `v1.82.3-stable` tag，基于该 tag 新建升级分支，再把 `routing-strategy` 自己的自定义提交按主题选择性回放到新基线上。这样可以把“上游升级”和“本地定制保留”拆开处理，减少无关冲突、生成物污染和回滚难度。

**技术栈：** Git、Python/pytest、LiteLLM 核心库与 proxy、Vitest、React dashboard、Prisma 驱动的 proxy 状态。

---

## 推荐策略

- 采用“新基线回放”而不是“旧分支直接合并上游”。
- 基线取 `v1.82.3-stable`，不再引入 `v1.82.3-stable.patch.4`。
- 将 `routing-strategy` 上的本地改动拆成三类：
  - 自定义 provider 与 provider 注册逻辑
  - stream timeout / streaming 兼容修复
  - 成本-延迟平衡路由策略与其 proxy/UI 配套
- 明确保留 `.claude/skills/...` 与 `handover.md` 这类协作资产，它们不影响运行时，但对后续接手、agent 工作流和知识沉淀有价值。
- `litellm/proxy/_experimental/out/` 与 `ui/litellm-dashboard/out/` 视为构建产物，在新基线上重新 build 验证，不直接回放旧分支里的产物文件。
- `ui/litellm-dashboard/public/assets/logos/*` 按源码引用做选择性保留，只带仍被自定义 provider 或 dashboard 源码实际引用的 logo。
- `ui/litellm-dashboard/package-lock.json` 仅在前端依赖图确实变化、构建失败或测试明确要求时再同步。
- `docs/strategy-debugging/` 如只是阶段性调试文档，可默认不进入最终升级分支；若上线排障仍依赖，再单独补回。

## 为什么这次不走旧方案

- `routing-strategy` 的祖先基线仍然是 `v1.80.11-nightly`。
- 从 `v1.80.11-nightly` 到 `v1.82.3-stable` 的上游增量非常大：
  - `4764 files changed, 627662 insertions(+), 103989 deletions(-)`
- 而当前 `routing-strategy` 自身相对旧基线也已经有明显定制：
  - `755 files changed, 11367 insertions(+), 374 deletions(-)`
- 仅核心热点文件，上游 stable 就已经发生了大规模变化：
  - `litellm/router.py`
  - `litellm/main.py`
  - `litellm/proxy/litellm_pre_call_utils.py`
  - `litellm/litellm_core_utils/streaming_handler.py`
  - `ui/litellm-dashboard/src/components/router_settings/index.tsx`
- 在这种前提下，如果直接把 `v1.82.3-stable` merge 到旧的 `routing-strategy`，冲突会把“上游升级”和“自定义功能保留”搅在一起，最终很难判断哪些行为是升级引入的，哪些是本地逻辑回归。

## 当前分支上需要保留的本地能力

### 必须保留的功能改动

- 自定义 provider 能力：
  - `377d76ffc` `add more providers`
  - `91b38b8c6` `add two gemini protocal providers`
  - `f7e90bf78` `add toapis providers`
  - `f15aa08c6` `add claude providers such as deerapi and funcloud`
  - `caf9d0b2b` `funcloud支持图片转base64`
- stream timeout / streaming 兼容修复：
  - `88716b109` `临时修复新版stream_timeout存在的bug`
- 成本/延迟平衡路由与配套集成：
  - `dcdfde4ca` `feat(routing): 添加 SLO-First 成本/延迟平衡自定义策略文档`
  - `21c299c03` `test(routing): 添加流式响应读取超时回退测试`
  - `7153110fa` `docs(routing): 添加 2026-04-01 至 2026-04-03 迭代评审文档`
  - `7f7528719` `update`
  - `42bc6796c` `feat(routing): 优化成本延迟平衡路由策略的元数据处理和配置选项`

### 明确保留的协作与资产类内容

- `a38452365` `add skill`
  - 保留 `.claude/skills/...`
- `b4efec32d` `add handover file`
  - 保留 `handover.md`
- `ac47ce126` `fix readme`
  - 保留 `handover.md` 的后续补充
- 自定义 provider 仍会引用到的 dashboard logo 资源
  - 以 `ui/litellm-dashboard/src/components/provider_info_helpers.tsx` 等源码引用为准，按需带入。

### 默认跳过的提交或内容

- `docs/strategy-debugging/`
  - 如只是阶段性调试文档，默认不带；若上线排障仍依赖，可单独补回。
- 所有 `litellm/proxy/_experimental/out/` 与 `ui/litellm-dashboard/out/` 下的生成产物
- `ui/litellm-dashboard/public/assets/logos/*` 中未被保留源码引用的素材
  - 只保留仍被自定义 provider 使用的 logo。
- `ui/litellm-dashboard/package-lock.json`
  - 除非前端依赖校验、构建或测试明确要求同步

### 需要先验证再决定是否回放的内容

- `88716b109` 的一行 `aiohttp_transport.py` 修改
  - 因为 `v1.82.3-stable` 自身已经大改了 `streaming_handler.py`，这个 hotfix 可能已经被上游等价覆盖
- `7153110fa` 中的代码改动
  - 虽然提交信息是 docs，但它还改了：
    - `litellm/litellm_core_utils/model_response_utils.py`
    - `litellm/litellm_core_utils/streaming_handler.py`
    - `tests/test_litellm/litellm_core_utils/test_model_response_utils.py`
    - `tests/test_litellm/test_router.py`
  - 因此不能简单按“纯文档提交”跳过

## 回放方式建议

- 不要对上述提交直接整批 `git cherry-pick` 到旧分支。
- 推荐在新的 stable 基线上使用：

```bash
git cherry-pick --no-commit <sha...>
```

然后显式还原不想要的文件，再做一次新的干净提交。

- 这次升级的目标不是保留原始 commit 边界，而是保留“运行时能力”。
- 因此允许把多个历史提交整理成几个主题提交：
  - `feat(custom-providers): replay local providers and collaboration assets on v1.82.3-stable`
  - `fix(streaming): preserve local stream-timeout behavior on v1.82.3-stable`
  - `feat(routing): replay cost-latency strategy on v1.82.3-stable`
  - `test(routing): restore local routing and streaming coverage on v1.82.3-stable`

### 任务 1：把 v1.82.3-stable 引入 litellm-new 并建立新基线

**Files:**
- Modify: `/Users/wenyu/Documents/code/litellm-new/.git/config`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/router.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/main.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/litellm_core_utils/streaming_handler.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/test_router.py`

- [ ] **Step 1: 确认当前工作区状态**

Run:

```bash
git status --short --branch
```

Expected: `routing-strategy` 处于干净状态，适合做基线升级工作。

- [ ] **Step 2: 添加源仓库 remote（如尚未存在）**

Run:

```bash
git remote add stable-src /Users/wenyu/Documents/code/litellm
```

Expected: 新增本地 remote 成功。

如果 `stable-src` 已存在，运行：

```bash
git remote get-url stable-src
```

Expected: 指向 `/Users/wenyu/Documents/code/litellm`。

- [ ] **Step 3: 只拉取 `v1.82.3-stable` tag**

Run:

```bash
git fetch stable-src refs/tags/v1.82.3-stable:refs/tags/v1.82.3-stable
```

Expected: `litellm-new` 本地已经可以引用 `v1.82.3-stable`。

- [ ] **Step 4: 校验 tag 指向的提交**

Run:

```bash
git show --no-patch --format='%H %ci %s' v1.82.3-stable
```

Expected: 输出提交 `61409275c8d8478d0a7ffc23d375a4fd86717b23` 及对应提交信息。

- [ ] **Step 5: 以 stable tag 建立新的升级工作分支**

Run:

```bash
git switch -c codex/routing-strategy-on-v1-82-3-stable v1.82.3-stable
```

Expected: 当前分支以 `v1.82.3-stable` 为起点，而不是旧的 `routing-strategy`。

- [ ] **Step 6: 记录旧分支和新基线的对照点**

Run:

```bash
git rev-parse routing-strategy
git rev-parse HEAD
```

Expected: 记录旧自定义分支头和新 stable 基线头，便于后续比较和回滚。

### 任务 2：回放自定义 Provider 能力，并保留必要协作资产

**Files:**
- Modify: `/Users/wenyu/Documents/code/litellm-new/.claude/skills/`
- Modify: `/Users/wenyu/Documents/code/litellm-new/handover.md`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/__init__.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/constants.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/litellm_core_utils/get_llm_provider_logic.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/main.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/apimart/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/bltcy/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/comflychat/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/deerapi/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/deerapi_claude/messages/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/deerapi_gemini/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/funcloud/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/funcloud_claude/messages/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/infiniai/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/ominilink_gemini/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/omnilink/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/onerouter/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/shubiaobiao/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/toapis/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/xiakexing/chat/transformation.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/src/components/provider_info_helpers.tsx`
- Modify: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/public/assets/logos/`
- Test: `/Users/wenyu/Documents/code/litellm-new/litellm/main.py`

- [ ] **Step 1: 以 no-commit 方式导入 provider 相关历史提交与 `.claude` 技能文件**

Run:

```bash
git cherry-pick --no-commit a38452365 377d76ffc 91b38b8c6 f7e90bf78 f15aa08c6 caf9d0b2b
```

Expected: provider 代码与 `.claude/skills/...` 进入工作区，但尚未生成正式提交。

- [ ] **Step 2: 丢弃不需要的生成物，但保留 `.claude` 与必要 logo**

Run:

```bash
git restore --staged --worktree litellm/proxy/_experimental/out
git restore --staged --worktree ui/litellm-dashboard/out
git restore --staged --worktree ui/litellm-dashboard/package-lock.json
```

Expected: 工作区保留 provider 代码、`.claude/skills/...`、必要注册逻辑，以及仍被 dashboard 源码引用的 logo；旧 build 产物被清掉。

- [ ] **Step 3: 解决 provider 注册冲突**

重点检查这些文件：

```text
litellm/__init__.py
litellm/constants.py
litellm/litellm_core_utils/get_llm_provider_logic.py
litellm/main.py
litellm/types/utils.py
ui/litellm-dashboard/src/components/provider_info_helpers.tsx
```

Expected: 新 provider 能在 `v1.82.3-stable` 的注册体系下正常暴露，不覆盖上游已有 provider 行为；dashboard 仅保留实际要展示的 provider 与 logo 引用，未被引用的 logo 继续从工作区剔除。

- [ ] **Step 4: 单独回放 handover 文档**

Run:

```bash
git cherry-pick --no-commit b4efec32d ac47ce126
```

Expected: `handover.md` 的本地协作信息进入工作区，但仍未形成正式提交。

- [ ] **Step 5: 提交整理后的 provider 与协作资产回放结果**

Run:

```bash
git add litellm .claude handover.md ui/litellm-dashboard/src/components/provider_info_helpers.tsx ui/litellm-dashboard/public/assets/logos/deerapi.jpeg ui/litellm-dashboard/public/assets/logos/infiniai.png ui/litellm-dashboard/public/assets/logos/bltcy.png ui/litellm-dashboard/public/assets/logos/xiakexing.jpeg ui/litellm-dashboard/public/assets/logos/shubiaobiao.png ui/litellm-dashboard/public/assets/logos/omnilink.png ui/litellm-dashboard/public/assets/logos/onerouter.png ui/litellm-dashboard/public/assets/logos/funcloud.png ui/litellm-dashboard/public/assets/logos/comflychat.png ui/litellm-dashboard/public/assets/logos/apimart.png ui/litellm-dashboard/public/assets/logos/toapis.png
git commit -m "feat(custom-providers): replay local providers and collaboration assets on v1.82.3-stable"
```

Expected: provider 系列改动、`.claude/skills/...`、`handover.md` 与必要 logo 收敛为一个干净提交。

### 任务 3：验证并回放 stream timeout / streaming 修复

**Files:**
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/custom_httpx/aiohttp_transport.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/litellm_core_utils/streaming_handler.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/test_router.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/litellm_core_utils/test_streaming_handler.py`

- [ ] **Step 1: 先在不移植 `88716b109` 的情况下运行 streaming 相关测试**

Run:

```bash
pytest tests/test_litellm/test_router.py -q -k "stream_timeout or empty_response_fallback"
pytest tests/test_litellm/litellm_core_utils/test_streaming_handler.py -q
```

Expected: 如果全部通过，说明 stable 可能已经覆盖了旧 hotfix 的问题。

- [ ] **Step 2: 如果失败，再按最小范围回放 `88716b109`**

Run:

```bash
git cherry-pick --no-commit 88716b109
git restore --staged --worktree .claude
```

Expected: 只保留 `litellm/llms/custom_httpx/aiohttp_transport.py` 中真正需要的兼容修复。

- [ ] **Step 3: 重新跑相关测试验证 hotfix 是否仍然必要**

Run:

```bash
pytest tests/test_litellm/test_router.py -q -k "stream_timeout or empty_response_fallback"
pytest tests/test_litellm/litellm_core_utils/test_streaming_handler.py -q
```

Expected: 如果第一次失败而第二次通过，就保留该 hotfix。

- [ ] **Step 4: 仅在确有必要时提交 streaming 修复**

Run:

```bash
git add litellm/llms/custom_httpx/aiohttp_transport.py
git commit -m "fix(streaming): preserve local stream-timeout compatibility on v1.82.3-stable"
```

Expected: 只把真正需要的一行或少量逻辑带上，不把旧分支的辅助文件一并回放。

### 任务 4：回放成本/延迟平衡路由核心能力

**Files:**
- Create: `/Users/wenyu/Documents/code/litellm-new/litellm/router_strategy/cost_latency_balanced.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/router.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/types/router.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/litellm_core_utils/model_response_utils.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/litellm_core_utils/streaming_chunk_builder_utils.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/litellm_core_utils/streaming_handler.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/llms/openai/openai.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/proxy/spend_tracking/spend_tracking_utils.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/router_unit_tests/test_cost_latency_balanced_routing.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/test_router.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/litellm_core_utils/test_model_response_utils.py`

- [ ] **Step 1: 用 no-commit 导入 routing 核心提交**

Run:

```bash
git cherry-pick --no-commit dcdfde4ca 21c299c03 7153110fa 7f7528719 42bc6796c
```

Expected: routing 逻辑、测试与部分 UI/proxy 配套进入工作区。

- [ ] **Step 2: 先移除不想保留的附带内容**

Run:

```bash
git restore --staged --worktree docs/strategy-debugging
git restore --staged --worktree litellm/proxy/_experimental/out
git restore --staged --worktree ui/litellm-dashboard/out
git restore --staged --worktree ui/litellm-dashboard/package-lock.json
```

Expected: 剩下的是 router、types、proxy、tests、必要前端源代码与必要构建脚本；不再携带旧 build 产物，也不误删已保留的 `handover.md`、`.claude` 或按需保留的 logo。

- [ ] **Step 3: 解决 backend 冲突并保留 stable 上的上游能力**

重点检查：

```text
litellm/router.py
litellm/main.py
litellm/types/router.py
litellm/litellm_core_utils/model_response_utils.py
litellm/litellm_core_utils/streaming_chunk_builder_utils.py
litellm/litellm_core_utils/streaming_handler.py
litellm/llms/openai/openai.py
litellm/proxy/spend_tracking/spend_tracking_utils.py
```

冲突处理原则：

```text
1. 以上游 v1.82.3-stable 的基础行为为底。
2. 只叠加 routing-strategy 的 SLO-First / 成本-延迟平衡策略能力。
3. 不回退 stable 已有的 router bugfix、参数定义或流式处理改进。
4. 7153110fa 中的 model_response_utils / streaming_handler 变更只保留与本地策略直接相关的部分。
```

- [ ] **Step 4: 提交 backend 路由能力**

Run:

```bash
git add litellm tests/router_unit_tests/test_cost_latency_balanced_routing.py tests/test_litellm/test_router.py tests/test_litellm/litellm_core_utils/test_model_response_utils.py tests/test_litellm/litellm_core_utils/test_streaming_handler.py
git commit -m "feat(routing): replay cost-latency strategy on v1.82.3-stable"
```

Expected: 本地路由核心能力已经建立在 stable 基线上。

### 任务 5：回放 proxy / dashboard 配套配置与测试

**Files:**
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/proxy/management_endpoints/router_settings_endpoints.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/proxy/proxy_server.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/types/management_endpoints/router_settings_endpoints.py`
- Modify: `/Users/wenyu/Documents/code/litellm-new/Dockerfile`
- Modify: `/Users/wenyu/Documents/code/litellm-new/docker/apk_add_with_retry.sh`
- Modify: `/Users/wenyu/Documents/code/litellm-new/docker/build_admin_ui.sh`
- Modify: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/build_ui.sh`
- Modify: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/src/components/router_settings/CostLatencyBalancedConfiguration.tsx`
- Modify: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/src/components/router_settings/ReliabilityRetriesSection.tsx`
- Modify: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/src/components/router_settings/index.tsx`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/proxy_unit_tests/test_router_settings_custom_strategy.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/proxy_unit_tests/test_ui_build_scripts.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/src/components/router_settings/index.test.tsx`

- [ ] **Step 1: 检查工作区是否已经包含 proxy/UI 相关改动**

Run:

```bash
git status --short
```

Expected: 来自任务 4 的 proxy/UI 文件如果仍未提交，就继续整理；如果已经提交完成，就进入精修阶段。

- [ ] **Step 2: 单独确认 router settings API 的类型与后端端点**

Run:

```bash
rg -n "cost_latency_balanced|custom_strategy|router settings" litellm/proxy/management_endpoints/router_settings_endpoints.py litellm/types/management_endpoints/router_settings_endpoints.py litellm/proxy/proxy_server.py
```

Expected: proxy 能暴露并消费新的自定义路由策略配置。

- [ ] **Step 3: 单独确认前端 router settings 入口**

Run:

```bash
rg -n "CostLatencyBalancedConfiguration|custom strategy|cost_latency_balanced" ui/litellm-dashboard/src/components/router_settings
```

Expected: dashboard 入口、配置组件和测试已接通。

- [ ] **Step 4: 如 Docker/UI build 脚本确有必要，再保留这些变更**

验证方式：

```bash
pytest tests/proxy_unit_tests/test_ui_build_scripts.py -q
```

Expected: 如果测试依赖新的 build 脚本逻辑，就保留 `Dockerfile`、`docker/build_admin_ui.sh`、`ui/litellm-dashboard/build_ui.sh` 等脚本更新；否则尽量少带。

- [ ] **Step 5: 提交 proxy / UI 配套**

Run:

```bash
git add litellm/proxy litellm/types/management_endpoints Dockerfile docker ui/litellm-dashboard/src/components/router_settings ui/litellm-dashboard/build_ui.sh tests/proxy_unit_tests/test_router_settings_custom_strategy.py tests/proxy_unit_tests/test_ui_build_scripts.py
git commit -m "feat(proxy-ui): replay routing strategy settings on v1.82.3-stable"
```

Expected: 后端配置接口与 dashboard 配置入口在 stable 基线上恢复一致。

### 任务 6：执行数据库前向升级与 schema 对账

**Files:**
- Modify: `/Users/wenyu/Documents/code/litellm-new/schema.prisma`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm/proxy/schema.prisma`
- Modify: `/Users/wenyu/Documents/code/litellm-new/litellm-proxy-extras/litellm_proxy_extras/migrations/`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/proxy_unit_tests/test_db_schema_migration.py`

- [ ] **Step 1: 先确认最终分支的 schema 目标是否仍以 stable 为准**

Run:

```bash
git diff --stat v1.82.3-stable -- schema.prisma litellm/proxy/schema.prisma litellm-proxy-extras/litellm_proxy_extras/migrations
```

Expected: 理想情况下，`schema.prisma` 不应再偏离 `v1.82.3-stable`；如果偏离，只能是这次 `routing-strategy` 回放确实新增了数据库对象，并且必须配套新增 migration 文件。

- [ ] **Step 2: 只有在 schema 真被本地功能改动时，才补新的 migration**

Run:

```bash
python3 ci_cd/run_migration.py routing_strategy_forward_upgrade
```

Expected: 如果 `schema.prisma` 相对现有 migration 真的有新差异，会在 `litellm-proxy-extras/litellm_proxy_extras/migrations/` 下生成一条新 migration；如果没有差异，就不应该额外提交 migration。

- [ ] **Step 3: 对旧数据库做前向升级前快照**

Run:

```bash
pg_dump --format=custom --no-owner --file /tmp/litellm-pre-v1-82-3.backup "$DATABASE_URL"
pg_dump --schema-only --no-owner --file /tmp/litellm-pre-v1-82-3-schema.sql "$DATABASE_URL"
```

Expected: 至少拿到一份可恢复的完整备份和一份升级前 schema 快照；如果使用云厂商托管库，也可以用库快照替代，但不能跳过这一步。

- [ ] **Step 4: 在 staging 或生产库克隆库上先看一眼真实 schema diff**

Run:

```bash
prisma migrate diff --from-url "$DATABASE_URL" --to-schema-datamodel ./schema.prisma --script
```

Expected: 这里大概率会看到大量“新增表 / 新增列 / 新增索引”的 SQL，而不是大批“同名字段类型不兼容”的冲突；这和我们前面分析一致，说明当前升级以前向补齐 stable schema 为主。

- [ ] **Step 5: 生产上按 LiteLLM 的前向迁移链路执行，不要退回 `db push`**

推荐方式：

```bash
DISABLE_SCHEMA_UPDATE=false python3 litellm/proxy/prisma_migration.py
```

如果是 Helm / K8s：

```text
1. 用单独的 migration job 或 Helm PreSync hook 跑迁移。
2. 迁移 job 上显式设置 DISABLE_SCHEMA_UPDATE=false。
3. 应用 Pod 上设置 DISABLE_SCHEMA_UPDATE=true，避免多副本并发跑迁移。
4. 不要传 --use_prisma_db_push；当前代码路径默认就是 prisma migrate deploy，只有显式传这个 flag 才会退回 db push。
```

Expected: 迁移通过 `prisma migrate deploy` 执行；如果运行环境是只读文件系统，额外设置 `LITELLM_MIGRATION_DIR` 指向可写目录。

- [ ] **Step 6: 按错误类型处理首次升级中的常见问题**

重点关注这些场景：

```text
1. P3005 + database schema is not empty
   - 说明旧库里已有 LiteLLM 表，但 migration history 不完整。
   - LiteLLM 会走 baseline + diff + resolve 流程；先在 staging 演练通过，再在生产跑。

2. P3018 + already exists / column already exists / relation already exists
   - 多半是幂等冲突，通常说明对象已存在。
   - 先核对 SQL 是否真已生效，再决定是否按 LiteLLM 的 resolve 逻辑标记为 applied。

3. P3018 + 42501 / permission denied / must be owner of table
   - 这是权限不足，不是幂等冲突。
   - 必须先补 ALTER / CREATE TABLE / CREATE INDEX 等权限，不能把失败 migration 硬标成成功。
```

Expected: 数据库问题按“幂等冲突”和“权限错误”分流处理，而不是一律手工跳过。

- [ ] **Step 7: 迁移后立刻做 schema 对账**

Run:

```bash
prisma migrate diff --from-url "$DATABASE_URL" --to-schema-datamodel ./schema.prisma --script --exit-code
pytest tests/proxy_unit_tests/test_db_schema_migration.py -q
```

Expected: `prisma migrate diff` 返回无差异，`test_db_schema_migration.py` 通过；说明当前分支的 schema、migration 和数据库最终状态已经对齐。

### 任务 7：进行聚焦验证并对账旧分支能力

**Files:**
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/router_unit_tests/test_cost_latency_balanced_routing.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/router_unit_tests/test_router_helper_utils.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/proxy_unit_tests/test_router_settings_custom_strategy.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/proxy_unit_tests/test_ui_build_scripts.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/test_router.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/litellm_core_utils/test_model_response_utils.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/tests/test_litellm/litellm_core_utils/test_streaming_handler.py`
- Test: `/Users/wenyu/Documents/code/litellm-new/ui/litellm-dashboard/src/components/router_settings/index.test.tsx`

- [ ] **Step 1: 跑 backend 核心测试**

Run:

```bash
pytest tests/router_unit_tests/test_cost_latency_balanced_routing.py -q
pytest tests/router_unit_tests/test_router_helper_utils.py -q
pytest tests/proxy_unit_tests/test_router_settings_custom_strategy.py -q
pytest tests/test_litellm/test_router.py -q -k "stream_timeout or empty_response_fallback"
pytest tests/test_litellm/litellm_core_utils/test_model_response_utils.py -q
pytest tests/test_litellm/litellm_core_utils/test_streaming_handler.py -q
```

Expected: 本地路由、stream timeout 和相关序列化/流式处理用例通过。

- [ ] **Step 2: 跑前端 router settings 定向测试**

Run:

```bash
npm --prefix ui/litellm-dashboard test -- src/components/router_settings/index.test.tsx
```

Expected: router settings 的新配置 UI 与表单交互测试通过。

- [ ] **Step 3: 跑 UI build 脚本测试**

Run:

```bash
pytest tests/proxy_unit_tests/test_ui_build_scripts.py -q
```

Expected: 如果保留了 build 脚本改动，这里必须通过。

- [ ] **Step 4: 与旧的 routing-strategy 做结果对账**

Run:

```bash
git diff --stat routing-strategy..HEAD
git range-diff 57e07bddd34185934893de3ad74583ba119ed67d..routing-strategy v1.82.3-stable..HEAD
```

Expected: 可以清楚回答：

```text
1. 旧分支有哪些本地能力被保留了？
2. 哪些只是文档/生成物，被有意丢弃？
3. 哪些 hotfix 被 stable 自身吸收，因此不再需要单独保留？
```

- [ ] **Step 5: 决定最终交付方式，而不是把新分支再 merge 回旧分支**

推荐方式：

```text
1. 把 codex/routing-strategy-on-v1-82-3-stable 作为新的接替分支。
2. 验证完成后，再决定是否用 force-with-lease 更新远端 routing-strategy。
```

不推荐方式：

```text
把这个新 stable 基线分支再反向 merge 回旧 routing-strategy。
```

原因：那样会把旧基线历史和新基线历史重新缠在一起，抵消这次“新基线回放”的价值。

## 已知风险

- `litellm/router.py`、`litellm/main.py`、`litellm/litellm_core_utils/streaming_handler.py` 是本次升级的最大冲突热点。
- `7153110fa` 看似文档提交，实际上夹带代码与测试变更，不能粗暴跳过。
- `88716b109` 是旧基线上的 hotfix，在 stable 上不一定还需要，必须以测试结果为准。
- 自定义 provider 提交里同时混入了 `.claude/skills`、dashboard 生成物和静态素材；其中 `.claude/skills` 需要保留，生成物必须剔除，logo 需要按源码引用精简。
- `v1.82.3-stable` 中并不存在这些本地 provider 目录，因此 provider 系列回放不会是“已上游合并”的轻量场景，而是完整的定制能力迁移。
- 当前数据库相对 stable 的主要差异是“缺表 / 缺列 / 缺索引”，不是大规模同名字段类型冲突；风险主要在首次 baseline、迁移权限和 migration history 缺失。
- 如果数据库过去主要通过 `db push` 建起来、没有完整 migration history，第一次升级到新 stable 时更容易触发 `P3005` baseline 流程，必须先在 staging 演练。

## 完成标准

- 新分支以 `v1.82.3-stable` 为真实基线，而不是旧 `routing-strategy`。
- 自定义 provider 能力被保留。
- 成本/延迟平衡路由核心、proxy 配置入口与 dashboard 配置入口被保留。
- stream timeout 兼容行为通过测试确认，而不是凭经验保留或删除。
- `.claude/skills/...`、`handover.md` 与确有源码引用的 logo 被保留；调试文档与旧 build 产物默认不进入最终升级分支。
- 数据库前向升级路径已经在 staging 或克隆库演练过一次，迁移后 `prisma migrate diff` 不再报 drift。
- 所有聚焦测试在新分支上通过。
