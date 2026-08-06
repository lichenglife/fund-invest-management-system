# CHANGELOG · FundLens

遵循 [Keep a Changelog](https://keepachangelog.com/)，按版本记录 Added/Changed/Fixed。

---

## [Unreleased] - 2026-08-06

### Added
- **数据库建表 DDL 交付文档**：`docs/.../15_数据库DDL/`（`数据库建表DDL.md` + `schema.sql`，alembic 迁移链离线生成 14 表 DDL，与 create_all 0 drift）
- **阶段评审报告**：`docs/.../14_阶段评审/REVIEW_20260806.md`（Phase 1 主体闭环，Go 有条件；重点记录口径冲突与质量逃逸）
- **P1-22 部署运行**：compose 生产化(ENV/Secrets/卷/健康检查/迁移/worker 常驻) + `scripts/init_db.py` 建表（§2.5/§9.1，`3f8d2be`）
- **P1-21 集成测试**：3 链路 6 用例（采集->质量 / ADR-002 评估->筛选->仪表盘 / 模拟->组合->诊断，`5dffcdb`）
- **P1-06b NL 解析 LLM 增强**：规则层移植 nl_baseline + LLM 编排(rule fast-path+LLM+normalize+clarify) + 160 条评测门禁；合并 strict=0.90≥0.85 实测 PASS；E6 裁决=TYPE 约束（`5ab00c2`）
- P1-11 Redis 缓存层 + P1-12 仪表盘聚合接口 + P1-09 实验室 + P1-08 组合诊断/回测/再平衡 + P1-07c/d/e 回本/定投/reset（`1387daf`~`ebd3a3a`）
- P1-13~19 前端 12+1 页契约对齐真实后端（`83f21a3`~`458175d`）
- `infra/external/llm_client.py` async DeepSeek 客户端 + `domain/nl_eval.py` 评测模块

### Changed
- **E6 红线口径**：稳健/低风险 由 exclude[index,etf] 改为 **TYPE 约束**(type∈[bond,mixed])，化解 §4 与 §12 评测 oracle 冲突（`5ab00c2`）
- Dockerfile/CI/Makefile 补装 `requirements-extras.txt`（原缺 pandas/akshare/alembic/APScheduler 等运行时依赖，`3f8d2be`）
- docker-compose.yml 生产化：密钥外部化(env_file+POSTGRES_*派生)、资源限制、migrate 一次性服务、worker 常驻调度、4 服务共享 fundlens-app 镜像（`3f8d2be`）
- **`scripts/init_db.py` 改走 alembic 迁移链**：干净库 `alembic upgrade head`、历史 create_all 库 `stamp head` 收编、head 库幂等；compose migrate 服务回归迁移链（P0-04b 修复后）
- `/api/screen/nl` 异步化：key 注入走 LLM 管线，无 key 规则兜底（`5ab00c2`）

### Fixed
- **P0-04b 迁移链损坏**：5 个 alembic migration 各 autogenerate 重复建全部核心表，干净库 `alembic upgrade head` 报 DuplicateTable。重写 4 个非初始迁移使其只建本任务拥有的表（e2de76->admin_users / 2467->data_quality_log / 742d->fund_dividends / f3a1->scheduler_jobs+2索引），bb11 初始 10 核心表不变。`alembic upgrade head` 干净 PG 库顺序通过（14 表+alembic_version），downgrade base/再 upgrade 均通过，与 `create_all` 逐列逐索引比对 0 drift。详见 DEFERRED D10 / REVIEW_20260806 A1。
- **scheduler_jobs.status/trigger 迁移漂移**：迁移中误带 `server_default`（模型用 Python `default=`），移除使迁移与 create_all 一致。
- **全量测试 49 DB ERROR**：`test_health.py`/`test_laboratory_api.py` 自建 create_engine+drop_all 污染共享引擎，改用 conftest 共享夹具；全量 518 passed/0 ERROR（`5dffcdb`）
- **.env.example 提交真实密钥**：TUSHARE_TOKEN/LLM_API_KEY 置空占位（§9 违规，历史 key 须轮换，`3f8d2be`）
- 任务分解文档状态失同步：P1-16a/17a/06b/20a/b 等标为实际已完成

### Known Issues (DEFERRED)
- D10 P0-04b 迁移链 **已修**（重写 4 迁移，alembic upgrade head 通过，0 drift）；D9 NL SLA **已随 P1-06b 闭环**(0.90)
- D6 adj_nav 临时回退 acc_nav（待真实复权，E3 近似）
- .env 密钥历史泄露（须轮换，git 历史不可删）
- D1/D2/D5/D7 延期项（不阻塞 Phase 1 主干）

---

## [Unreleased] - 2026-07-30

### Added
- **阶段评审报告**：`docs/.../14_阶段评审/REVIEW_20260730.md`（首阶段评审，Go 结论）
- P1-07b 分红复权+赎回费（E3 红线，`bdb590c`）
- P1-07a 模拟交易账户/买卖（§8.4 原子事务，`9895c8b`）
- P1-06a/b/c 智能筛选器全闭环（表单/NL/去重，`17ec374`~`8a69f74`）
- P1-05 夜算批（分位表+多进程评分，`981d48c`）
- P1-04a/b 评估接口 5 端点（`a903ff7`/`614b123`）
- P1-03a/b/c/d 评估引擎算法全闭环（E1/E2/E4/E5/E7/E10，`2da6ccc`~`9736c25`）
- P1-01a/b/c/d 采集全链路（AkShare/Tushare/清洗/upsert/调度/锁，`0b748b7`~`b5d1f85`）
- P0-05 鉴权骨架（AES-256 + AES 令牌，`b913d85`）
- P0-04 SQLAlchemy 模型 + Alembic 迁移（10 核心表，`d5cab55`）
- P0-03/06/07 工程骨架（仓库/compose/CI/信封/日志/Streamlit 壳，`0db5a1e`）

### Fixed
- review 修复 /score 恒 None + attribution 误导 0 + 闰年崩溃（`4cfe299`）
- upsert_funds 分批（PG 参数上限 65535，`5937f35`）
- P1-06b E6 排除用 not_in 完整排除 index/etf（`d990dfe`）

### Known Issues (DEFERRED)
- D6 adj_nav 临时回退 acc_nav（待真实复权，E3 近似）
- D9 NL 规则层 82% 未达 85% SLA（待 LLM key C1）
- D1/D2/D5/D7 延期项（不阻塞 Phase 1 主干）
