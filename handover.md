# LiteLLM 项目交接文档

本文档用于项目交接，说明当前分支情况、常用运维流程（含新增协议供应商）、打包方式及部署参考。

> **⚠️ 重要：本仓库为 Public 仓库**
>
> 代码与文档对所有人可见，**严禁**提交或提及：API Key、密码、内部环境地址、未脱敏配置、业务敏感信息等。敏感配置与部署脚本请放在 **guru-litellm** 等私有仓库。

---

## 1. 当前分支说明

| 分支 | 说明 |
|------|------|
| `main` | 主分支，与上游 LiteLLM 对齐 |
| `feat/v2.1.1-based-on-v1.80.11-stable` | 基于 v1.80.11-stable 的功能分支 v2.1.1 |
| `feat/v2.1.2-based-on-v1.80.11-stable` | 基于 v1.80.11-stable 的功能分支 v2.1.2 |
| `feat/v3.1.1-based-on-v1.80.11-stable` | 基于 v1.80.11-stable 的功能分支 v3.1.1 |
| `feat/v3.1.2-based-on-v1.80.11-stable` | 基于 v1.80.11-stable 的功能分支 v3.1.2 |
| `feat/v3.1.3-based-on-v1.80.11-stable` | 基于 v1.80.11-stable 的功能分支 v3.1.3 |
| **`feat/v3.1.4-based-on-v1.80.11-stable`** | **当前主开发分支**（基于 v1.80.11-stable 的 v3.1.4） |

- 远程：`origin` 对应主仓库，`old-repo` 为历史远程。
- **迭代方式**：每次迭代都是在上一个版本分支的基础上继续开发（例如 v3.1.4 基于 v3.1.3，再之前 v3.1.3 基于 v3.1.2），而不是固定在一个分支上开发再合并到其他分支。

---

## 2. 线上两套环境

| 环境 | Dashboard 地址 | 用途 |
|------|----------------|------|
| **生产** | https://litellm.thebetter.ai/ui | 正式对外服务 |
| **测试** | https://test-litellm.thebetter.ai/ui | 预发/联调验证 |

- 配置、域名与部署脚本不在本仓库，在 **guru-litellm** 中维护（见下文「部署参考」）。

---

## 3. 常用运维流程：增加协议供应商

新增 **OpenAI 兼容**、**Gemini**、**Claude（Anthropic Messages）** 协议供应商时，请严格按项目内技能文档操作，避免漏步骤导致「Unsupported provider」或模型不展示等问题。

### 3.1 详细步骤所在位置（必读）

所有「新增供应商」的**完整步骤、代码模板、修改文件清单**均在项目根目录 **`.claude/skills/`** 下，按协议类型对应：

| 协议类型 | 技能目录 | 说明 |
|----------|----------|------|
| **OpenAI 兼容**（`/v1/chat/completions`） | [.claude/skills/add-openai-provider/SKILL.md](.claude/skills/add-openai-provider/SKILL.md) | 常量、枚举、transformation、main.py、get_llm_provider_logic、UI 配置、打包与本地验证 |
| **Gemini** | [.claude/skills/add-gemini-provider/SKILL.md](.claude/skills/add-gemini-provider/SKILL.md) | 继承 `GoogleAIStudioGeminiConfig`、参数映射、成本计算、UI、打包与本地验证 |
| **Claude（Anthropic Messages）**（`/v1/messages`） | [.claude/skills/add-claude-provider/SKILL.md](.claude/skills/add-claude-provider/SKILL.md) | 继承 `AnthropicMessagesConfig`、ProviderConfigManager、main.py、图片 base64 等 |

**操作前请先通读对应 SKILL.md**，按其中「信息收集 → 步骤 → 文件变更汇总」执行，并做本地验证。

### 3.2 流程概要（三协议共用部分）

1. **信息收集**  
   向需求方确认：供应商名称（小写下划线）、显示名称、API Base、环境变量名、默认模型、Logo 等（各协议 SKILL 中有清单）。

2. **代码与配置**  
   - 在 `litellm/types/utils.py` 的 `LlmProviders` 中增加新供应商（三协议都必须）。  
   - 按协议在对应文件里：加 transformation/config、completion 分支、供应商检测（若需要）、UI 配置（`provider_create_fields.json` + `provider_info_helpers.tsx`）。  
   - Claude 协议若后端仅支持 base64 图片，需按 add-claude-provider 中「图片 URL 转 base64」两处路径修改。

3. **UI 构建与缓存**  
   修改了 UI 相关配置后必须执行：
   ```bash
   cd ui/litellm-dashboard
   npm run build
   cp -r out/* ../../litellm/proxy/_experimental/out/
   rm -rf /tmp/litellm_ui   # 清除 UI 缓存
   ```

4. **本地验证**  
   使用 **guru-litellm** 中的本地配置启动（见下）：
   ```bash
   poetry run litellm --config ../guru-litellm/configs/proxy_config_local.yaml --debug --detailed_debug
   ```

5. **打包与推送**  
   见下文「修改代码后如何打包」。

### 3.3 常见问题速查

- **模型从数据库加载后不显示** → 检查 `LlmProviders` 是否包含该供应商。  
- **Unsupported provider** → 检查 `provider_create_fields.json` 的 `provider` 与 `provider_info_helpers.tsx` 中枚举/`provider_map` 键名是否一致（Claude/Gemini SKILL 中强调）。  
- **请求未打到正确 API Base** → 查对应协议的 endpoint/前缀检测及 transformation 中的 api_base/api_key 逻辑。  

更多 FAQ 见各 SKILL.md 的「常见问题」与「文件变更汇总」。

---

## 4. 修改代码后如何打包

在项目**根目录**执行以下流程，将镜像构建为 **linux/arm64** 并推送到当前使用的 ECR。

### 4.1 打包与推送命令

```bash
# 将 TAG 替换为实际版本号（如 v3.1.4、20250206）
export TAG=your-tag

# 构建镜像（linux/arm64）
docker build --platform=linux/arm64 -t 851725654066.dkr.ecr.us-east-1.amazonaws.com/saas-guru/litellm:$TAG .

# 若未登录 ECR，先登录
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin 851725654066.dkr.ecr.us-east-1.amazonaws.com

# 推送到 ECR
docker push 851725654066.dkr.ecr.us-east-1.amazonaws.com/saas-guru/litellm:$TAG
```

- 使用的 Dockerfile：仓库根目录的 **`Dockerfile`**（会执行 Admin UI 构建、Python 包构建与安装）。  
- 镜像名与 ECR 地址以当前使用的为准；若后续变更，以 **guru-litellm** 中部署脚本/配置为准。

---

## 5. 部署参考（guru-litellm）

- **配置与部署脚本不在本仓库**，在 **guru-litellm** 仓库中。  
- 本仓库仅通过相对路径引用 guru-litellm 的**本地配置**做本地联调，例如：
  ```bash
  poetry run litellm --config ../guru-litellm/configs/proxy_config_local.yaml --debug --detailed_debug
  ```
  即假定项目与 guru-litellm 同层级：`../guru-litellm/`。

在 guru-litellm 中可找到：

- **配置文件**：如 `configs/proxy_config_local.yaml` 等，用于本地/测试/生产环境。  
- **部署脚本**：如何将镜像 `851725654066.dkr.ecr.us-east-1.amazonaws.com/saas-guru/litellm:$TAG` 部署到：
  - https://litellm.thebetter.ai  
  - https://test-litellm.thebetter.ai  

具体部署步骤、环境变量、Ingress/Service 等以 **guru-litellm** 内文档和脚本为准。本仓库只负责「代码 + 构建镜像并推到 ECR」，不负责 K8s/ECS 等编排细节。

---

## 6. 小结

| 事项 | 位置/方式 |
|------|------------|
| 当前主开发分支 | `feat/v3.1.4-based-on-v1.80.11-stable` |
| 生产 / 测试 UI | https://litellm.thebetter.ai/ui 、 https://test-litellm.thebetter.ai/ui |
| 新增 OpenAI 协议供应商 | 严格按 [.claude/skills/add-openai-provider/SKILL.md](.claude/skills/add-openai-provider/SKILL.md) |
| 新增 Gemini 协议供应商 | 严格按 [.claude/skills/add-gemini-provider/SKILL.md](.claude/skills/add-gemini-provider/SKILL.md) |
| 新增 Claude 协议供应商 | 严格按 [.claude/skills/add-claude-provider/SKILL.md](.claude/skills/add-claude-provider/SKILL.md) |
| 打包 | 项目根目录 `docker build --platform=linux/arm64 -t ... .`，再 push 到 ECR |
| 部署配置与脚本 | **guru-litellm** 仓库 |

如有分支策略或环境域名变更，请同步更新本文档。
