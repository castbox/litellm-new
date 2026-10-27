# v1.106.4 定制版数据库迁移操作说明

适用于线上定制提交 `9e104f270e1dc9dee6c96398b4109e0eba120f20` 升级到本分支，官方目标基线为 `ea7ca16dbc3904d9e59a9505f379a2ca3091821f`。本文是发布演练及执行依据，本次开发没有对生产数据库执行这些操作

## 先核对迁移历史

旧定制目录有 110 份迁移，新官方目录有 213 份，其中 107 份同路径脚本完全一致。本分支新增一份向前迁移，最终执行目录有 214 份。历史文件数不等于待执行次数，发布前需导出实际 `_prisma_migrations` 的名称、校验和和完成状态，并与固定源码及实际结构核对

下列三份旧迁移不复制进新目录，已执行的记录及校验和保留在数据库历史表中

| 旧迁移 | 处理原因 |
| --- | --- |
| `20260311180521_schema_sync` | 含旧结构同步和 MCP 字段移除，不能重新执行来覆盖新版结构 |
| `20260416210000_restore_mcp_submission_fields` | 新版 schema 及官方迁移已包含相关 MCP 审核字段；原脚本还改历史行，不作为本次启动迁移重复运行 |
| `20260520000000_add_model_group_to_daily_spend_unique_keys` | 原样保留已执行历史，最终结构由新的向前迁移衔接 |

不要删除历史记录、改写旧 SQL 校验和或把失败迁移全部标记为成功。若实际迁移记录存在失败、缺项或 checksum 差异，先解释原因和结构状态，再制定该库的恢复步骤

## 本次向前迁移做什么

`20261027000000_preserve_daily_spend_model_group` 处理用户、团队、组织、终端用户、Agent、标签六类每日支出表。它将已有 `model_group` 字段的未来默认值设为空字符串，并确保唯一索引同时包含实体、日期、API key、底层模型、对外模型名、供应商、MCP 工具名、endpoint

迁移识别实际索引列，不仅凭索引名称判断。已经正确的索引保留，必要时改回旧定制索引名；存在官方粗粒度索引时删除它，再保证含 `model_group` 的唯一规则。已有两个索引并存的情况也在本地演练范围中。重复执行不会重建已经正确的索引

迁移不 UPDATE、DELETE 或回填历史 NULL，不会把以前合并的支出拆开。若新索引因历史重复而无法创建，应停止执行并单独处理数据问题，不在启动迁移中加无边界数据清理。创建和移除索引仍有锁影响，需按生产数据规模演练并安排窗口

三份 schema 必须保持内容一致：根目录、`litellm/proxy` 和已安装的 `litellm_proxy_extras`。生成的 Prisma 客户端也必须来自同一结构，不能在旧客户端上只替换 SQL

## 共库升级顺序

1. 固定新、旧定制镜像 digest，备份数据库及迁移历史，在生产副本完成全部待执行迁移和结构差异检查，并验证备份可恢复
2. 在两版应用配置中设置并验证 `DISABLE_SCHEMA_UPDATE=true`，同时核对 `general_settings.disable_prisma_schema_update` 的实际取值；最好使用不具备 DDL 权限的应用账号。覆盖旧实例重启、扩容、回退和其他结构管理入口
3. 暂停相互争用的迁移入口，由单一迁移任务使用新定制镜像及迁移专用连接执行。运行时采用新版默认 v2 resolver，不使用 `--use_legacy_migration_resolver`，不执行 `prisma db push --accept-data-loss`
4. 迁移成功后核对六类索引、MCP 审核数据、历史支出和迁移 checksum。新版请求日志的两个索引由官方后台构建机制创建，可在演练中等待其完成后再作完整 schema diff
5. 使用旧、新客户端对同库读写，验证同一底层模型的两个业务名称分别累计，覆盖 endpoint、MCP、空名称、并发写入和重试。确认后才进行小流量和滚动替换
6. 验证回退到旧应用镜像时仍保持禁止自动 DDL。应用回退不等于反向删除新表和新列；共库兼容不满足时，按升级设计改用隔离数据库方案

以下为隔离演练库中的单任务命令示例，连接值从受控环境注入。生产执行前要将目标绑定到批准的库、schema 和迁移账号

```sh
prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
prisma migrate deploy --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
prisma migrate status --schema litellm-proxy-extras/litellm_proxy_extras/schema.prisma
```

`DATABASE_URL` 和 `DIRECT_URL` 必须指向同一目标库，迁移连接直连数据库，不能经过事务池。若通过 Python 启动迁移管理器，要显式传入 `use_migrate=True, use_v2_resolver=True`；CLI 默认 v2 不代表 Python 方法的默认参数也为 v2

## 已完成的本地证据

单测与真实 PostgreSQL 测试覆盖六类表、官方粗索引、旧定制正确索引、两者并存、重复执行、历史 NULL 保持，以及并发按对外名称写入

另一次完整演练从旧定制 schema 建库，将旧 110 条 SQL 的 SHA-256 写入合成 ledger，再执行新目录中的待执行迁移。完成后 ledger 共 217 条，旧 110 条 checksum 和插入的支出、MCP 审核测试数据均保持不变，再次 deploy 没有待执行项。217 包含新目录 214 项和仅在旧 ledger 中保留的 3 项，不能据此推断生产 ledger 必然也是 217 条

官方请求日志索引构建完成后，根目录、Proxy 和扩展包三份 schema 的 `prisma migrate diff --exit-code` 都返回 0、empty migration。仓库的禁止迁移批量改写数据检查通过

本地证据不覆盖生产数据分布、数据量、索引锁等待和双版本应用共库的全部行为，这些内容应保留在发布验收中
