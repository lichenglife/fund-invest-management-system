# CHANGELOG · FundLens

遵循 [Keep a Changelog](https://keepachangelog.com/)，按版本记录 Added/Changed/Fixed。

---

## [Unreleased] - 2026-08-06

### Added
- **任务执行监控闭环（A3 业务片 / §3.14.3 scheduler_jobs / §3.14.5 失败告警）**：新增 `domain.scheduler.record_job_run` 上下文管理器——开始即写 `status=running` 行、正常退出写 `success`+`result_summary`+`duration_ms`、异常写 `failed`+`error`(摘要截断 2000，§9 不存堆栈/SQL)并 **re-raise**；用**独立 session**(业务事务回滚仍保留执行记录)；`session_factory` 可注入(懒导入 infra，测试隔离)。接线 `workers/collect.py`(collect_all)+`workers/batch.py`(fund_recalc)，定时 `cron` 与手动 `manual` 区分 trigger 落库；`POST /admin/trigger-job` 参数校验先于记录(避免坏请求污染执行历史)。新增 `GET /api/v1/admin/jobs`(按 `started_at` 倒序，`days`/`limit` 过滤，7 字段信封，字段对齐前端 mock `ADMIN_JOBS`；须管理员 §2.19.6)。14 单测通过(recorder 7 + admin_jobs 7)。**范围**：仅任务执行结果落库 + 前端可查；§2.16 Prometheus 监控 / §2.14 备份 / `/monitor` 运维端点仍搁置(DEFERRED S1/S2/S6)。
- **stylebox 风格箱算法（P1-04a 闭环 / TP-01 §3.5 / 闭合 E13 / DC-003）**：新增 `domain/stylebox.py` 九宫格(size 大/中/小 × value_growth 价值/平衡/成长)，持仓法(市值分布定 size + 估值/成长因子定 value_growth)+ 收益回归交叉验证(numpy OLS，载荷不显著 `|load|<0.3 且 p>0.1` -> `cv_flag=True`)；E13 限权益类(stock/mixed/index/etf)，债/货/QDII 不显示；回退链(基金披露风格 `is_proxy` / 持仓基本面缺失 / 无持仓)，同 PEG/ERP 代理范式降级 `available=False` 不硬算。接线 `/api/v1/funds/{code}/stylebox` 端点 + 组合诊断⑥风格维(`diagnose(fund_styles=...)`)。30 单测通过(domain 覆盖率 93%)。
- **数据库建表 DDL 交付文档**：`docs/.../15_数据库DDL/`（`数据库建表DDL.md` + `schema.sql`，alembic 迁移链离线生成 14 表 DDL，与 create_all 0 drift）
- **阶段评审报告**：`docs/.../14_阶段评审/REVIEW_20260806.md`（Phase 1 主体闭环，Go 有条件；重点记录口径冲突与质量逃逸）
- **P1-22 部署运行**：compose 生产化(ENV/Secrets/卷/健康检查/迁移/worker 常驻) + `scripts/init_db.py` 建表（§2.5/§9.1，`3f8d2be`）
- **P1-21 集成测试**：3 链路 6 用例（采集->质量 / ADR-002 评估->筛选->仪表盘 / 模拟->组合->诊断，`5dffcdb`）
- **P1-06b NL 解析 LLM 增强**：规则层移植 nl_baseline + LLM 编排(rule fast-path+LLM+normalize+clarify) + 160 条评测门禁；合并 strict=0.90≥0.85 实测 PASS；E6 裁决=TYPE 约束（`5ab00c2`）
- P1-11 Redis 缓存层 + P1-12 仪表盘聚合接口 + P1-09 实验室 + P1-08 组合诊断/回测/再平衡 + P1-07c/d/e 回本/定投/reset（`1387daf`~`ebd3a3a`）
- P1-13~19 前端 12+1 页契约对齐真实后端（`83f21a3`~`458175d`）
- `infra/external/llm_client.py` async DeepSeek 客户端 + `domain/nl_eval.py` 评测模块

### Changed
- **MVP 优先级调整（2026-08-07）**：优先业务功能、尽快 MVP 落地；非业务项暂时搁置并记录。P1-23 拆为 P1-23a 灰度上线（业务，优先）+ P1-23b 监控/备份（非业务，搁置）。搁置清单见 `DEFERRED.md` §搁置项（S1~S7：监控/备份/CR流程/CI-PG/全量构建验证/后台运维端点）。不搁置：A2 密钥轮换、后台 /admin/jobs+/quality、stylebox 算法、D6 复权（均业务/上线必做）。
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
- **CR-20260806-01**（前端生产级改造评估，C2，**Approved（2026-08-06）**）：依《需求变更管理规范》对 `feat/frontend-ui` 前端做八维（颜色/组件/样式/大小/部署/联动/审美/合理性）评估，新增 `13-需求变更管理规范/cr/` 目录并落盘 CR + 影响分析 + 重新设计与改造方案三件。核心发现：涨跌配色语义自相矛盾（`utils.pct_color` 红涨绿跌 vs 令牌翠绿=正）、令牌未单一源落地（13 处裸 `#6B7280` + 游离色 `#fdeeee/#f0d39a/#8a5a00`）、无响应式/可访问性基线、全站仍走 Mock 未联调。不触动 DB / 接口契约 / E1–E14 口径。详见 `13-需求变更管理规范/cr/CR-20260806-01_*.md`。
- **CR-20260806-01 实现(令牌 v2 地基)**：落地红涨绿跌语义——`style.css` 重定义为令牌 v2 单一源（新增涨跌语义色 `--color-gain` 红 / `--color-loss` 绿 + 间距/字号阶梯/阴影层级/焦点环令牌 + 响应式 `@media` 断点 + 可访问性 AA 基线）；`utils.pct_color` 与 `components/kpi_card` 单向对齐令牌；品牌翠绿降级为纯标识色，禁用于涨跌数值。不触动 DB/接口契约/E1–E14。分支 `feature/cr-20260806-01-frontend-overhaul`；新增 `tests/test_frontend_tokens.py` 锁死语义一致性。
- **CR-20260806-01 实现(#8 逐页/组件着色收敛)**：消除全部游离硬色码（04 筛选器 `#f0d39a/#8a5a00`、03 详情 `#eef9f3/#fff8ec/#fdeeee` 等），统一引用 `style.css` 令牌 v2；`score_panel` 复合分改走 `LEVEL_COLOR` 状态色（与红涨绿跌绝缘）；`05_模拟交易` 持仓市值改 `COLOR_GREEN_D` 品牌标识色；新增令牌 `--warn-border/--brand-border/--surface-2/--neutral-bg`；扩展 `tests/test_frontend_tokens.py` 至 6 项（含 `test_no_inline_hex_outside_utils` 锁死游离色）并全绿；`style_box`/`ui`/`app.py`/`09舆情`/`13后台` 等组件与页面完成令牌替换，`py_compile` 全绿。
- **CR-20260806-01 实现(#9 响应式移动优先与可访问性逐页落地)**：新增视口桥 `ui.inject_responsive_bridge()`（将 `<html data-fl-view>` 置为 sm/md/lg，纯 CSS 响应式，免 Python 感知屏宽）；新增 `ui.kpi_grid()` 响应式网格（auto-fit，替代 `st.columns(N)`+`kpi_card` 循环，宽屏多列/平板 2 列/手机单列）；`style.css` 新增 `.fl-grid` + `[data-fl-view="sm"]` 手机端将全部 `st.columns` 堆叠为单列 + `#main-content` 焦点清理；`page_header` 每页注入「跳到主内容」跳转链接与 `#main-content` 无障碍地标（AA 焦点环/减弱动效/屏幕阅读器专用已就绪）；01 仪表盘、13 后台管理 KPI 行改 `kpi_grid`；`kpi_card` 抽离 `kpi_card_html` 供网格拼接；`tests/test_frontend_tokens.py` 扩至 10 项（a11y 跳转链接/焦点环、响应式网格/视口桥断言）全绿。其余页面列布局由全局 `sm` 堆叠规则统一覆盖移动端。
- **CR-20260806-01 关闭（2026-08-07）**：实现范围（令牌 v2 / 配色收敛 #8 / 响应式+a11y #9）已交付并合入 `feature/cr-20260806-01-frontend-overhaul`（commit `7dee044`）；CR 状态置 **Closed**。部署交付口径 + 前后端联调依《需求变更管理规范》§7 部分落地登记 **DEFERRED D11** 跟踪，不静默丢弃；CI 门禁依用户决策不纳入本 CR（前端令牌一致性测试 `tests/test_frontend_tokens.py` 10/10 已随提交合入）。

### Fixed
- review 修复 /score 恒 None + attribution 误导 0 + 闰年崩溃（`4cfe299`）
- upsert_funds 分批（PG 参数上限 65535，`5937f35`）
- P1-06b E6 排除用 not_in 完整排除 index/etf（`d990dfe`）

### Known Issues (DEFERRED)
- D6 adj_nav 临时回退 acc_nav（待真实复权，E3 近似）
- D9 NL 规则层 82% 未达 85% SLA（待 LLM key C1）
- D1/D2/D5/D7 延期项（不阻塞 Phase 1 主干）
