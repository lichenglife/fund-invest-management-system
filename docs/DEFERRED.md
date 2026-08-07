# 搁置项与待澄清问题记录（DEFERRED）

> 本文件记录开发推进中**发现但暂未处理**的问题，遵循 CLAUDE.md「严格执行既有技术方案，有问题处记录搁置、不影响推进」。
> 每项标注：发现来源 / 性质 / 影响 / 建议处置时点。解决后划掉并标注 commit。

---

## D1 · navs 表分区策略未落地

- **发现来源**：详设 §2.20.2 `navs` DDL 给定 `PARTITION BY RANGE (trade_date)`，但**未定义子分区**（按年/按月的分区表结构）。
- **性质**：文档不完整（运维层细节缺失），非算法口径问题。
- **当前处理**：P0-04 模型与迁移先建普通表（无分区声明），保证 PK/FK/索引正确。
- **影响**：数据量大时查询性能不如分区；MVP 单用户数据量小，不阻塞。
- **建议处置时点**：P1-22 部署运行期，结合 §2.12 存储需求与 pg_partman 落地按年分区迁移（单独 `alembic revision`）。
> 📌 **状态：延期项（非缺陷）**。`navs` 分区子策略（按年，pg_partman 自动建子分区）计划 P1-22 部署期落地；MVP 阶段建普通表（数据量小，性能可接受），已在 §2.20.2 `navs` DDL 注释标注。

---

## D2 · 其余 22 张表字段未定义

- **发现来源**：详设 §2.20.3 仅罗列表名（managers / fund_dividends / discovery_entries / field_glossary / macro_indicators / market_sentiment / external_signal / sentiment_news / stock_financials / rag_documents / ai_weekly_reports / risk_assessments / alerts / valuation_signals / data_quality_log / notes / learning_paths / case_scenarios / case_replay_logs / behavior_assessments / data_collection_jobs / scheduler_jobs），"字段以 §3.x.4 为准"，但 §3.x.4 各处**仅罗列表名，无字段 DDL**。
- **性质**：文档不完整（字段定义缺失），需在实现对应模块时补字段设计。
- **当前处理**：P0-04 仅交付 §2.20.2 明确的 10 核心表；22 表待各自模块落地时补建。`admin_users`(P0-05)与 `data_quality_log`(P1-01c，技规§3.2 DDL)已补。
- **影响**：对应模块（P2 宏观/风险/学习、P3 穿透/AI）开工前需补表设计；不阻塞当前 Phase 1 主干（评估/采集/筛选/模拟/组合）。
- **建议处置时点**：各模块任务开工前（如 P2-01 宏观前补 macro_indicators 表），逐表加迁移。
> 📌 **状态：延期项（非缺陷）**。22 张扩展表字段 DDL 在各模块任务开工前随 §3.x 数据库设计补充（已在 §2.20.3 注记），不阻塞 Phase 1 主干。

---

## D3 · scores 表五因子口径文档冲突

- **发现来源**：§2.20.2 `scores.weights` 注释与 §2.21.2 响应示例仍为旧口径 `ret/risk/style/cost/scale`（E4/E5 修订**前**）；CLAUDE.md §4 红线（最高优先级）规定新口径 `ret/risk/perf/scale/manager`（E4/E5 闭环）。
- **性质**：文档未同步修订（详设 §2.20.2/§2.21.2 与 CLAUDE.md §4 不一致）。
- **当前处理**：表结构（JSONB `weights`/`factors`）不变；**代码与测试一律用新口径** `ret/risk/perf/scale/manager`（见 `infra/db/models/fund.py` Score 注释、`tests/test_models.py` test_scores_jsonb_roundtrip）。
- **影响**：仅注释/示例文字层面，不影响表结构与算法。
- **建议处置时点**：文档统一修订时（F2 类）同步详设 §2.20.2/§2.21.2 注释为新口径。
> ✅ **已解决 @ 7612a5e**：详设 §2.20.2 `scores.weights` 注释与 §2.21.2 响应示例口径已统一为 `ret/risk/perf/scale/manager`（权重对齐 `SCORE_WEIGHTS={ret:20,risk:25,perf:20,scale:15,manager:20}`），与代码侧 `infra/db/models/fund.py`、CLAUDE.md §4 红线一致。

---

## D4 · CLAUDE.md / 开发规范 信封字段简写与权威源不一致

- **发现来源**：权威详设 §2.21.1（S4 闭环）+ §5.2 定义信封为 **7 字段** `{code, data, source, as_of, disclaimer, message, trace_id}`；但 CLAUDE.md §6 与 开发规范 §6.2 的简写示例漏列 `disclaimer`（6 字段）。
- **性质**：文档简写不完整。
- **当前处理**：代码实现 **7 字段**（`schemas/envelope.py`，`disclaimer` 默认"仅供参考，不构成投资建议"）；CLAUDE.md §3 文档地图路径（`/workspace/` vs `docs/`）亦在途未提交修改。
- **影响**：无功能影响；仅文档与代码表述需对齐。
- **建议处置时点**：文档统一修订时补 `disclaimer` 字段；CLAUDE.md §3 路径修正为实际嵌套路径 `docs/基金评估系统_交付文档/<NN>_*/`。
> ✅ **已解决 @ 7612a5e**：`schemas/envelope.py` 本为 7 字段（含 `disclaimer`）已正确；本次补 CLAUDE.md §6 与 开发规范 §6.2 简写示例的 `disclaimer` 字段，三处信封定义一致。CLAUDE.md §3 文档地图路径已由远程 Phase 0 提交修正为 `docs/基金评估系统_交付文档/<NN>_*/`。

---

## D5 · 宿主端口避让（环境事实，非文档问题）

- **发现来源**：本机已存在常驻容器 chroma(8000) / postgres:16-alpine(5432) / redis:7-alpine(6379)，占用标准端口。
- **当前处理**：`docker-compose.yml` 宿主端口映射避让为 API 18000 / Streamlit 18501 / PG 15432 / Redis 16379（容器内端口不变，服务间用 compose 服务名互联）。README 已注明。
- **影响**：仅本机访问端口变化；CI/容器内无影响。
- **建议处置时点**：若既有容器移除，可改回标准端口映射。
> 📌 **状态：环境事实，已处理**。`docker-compose.yml` 宿主端口已避让（API 18000 / Streamlit 18501 / PG 15432 / Redis 16379），CI/容器内无影响，无需仓库变更。

---

## D6 · AkShare/Tushare 净值 acc_nav/adj_nav 口径

- **发现来源**：P1-01a 核实 AkShare 运行时接口。`fund_open_fund_info_em(indicator="单位净值走势")` 仅返回单位净值，无累计/后复权净值；§2.20.2 `navs` 要求 `nav/acc_nav/adj_nav`（`adj_nav` NOT NULL）。
- **性质**：数据源口径缺口（非算法口径）；后复权净值涉及 E3 红线（分红复权）。
- **当前处理**（P1-01c 更新）：
  - `acc_nav`（累计净值）：已补——adapter `fetch_nav` 合并 `累计净值走势` indicator（AkShare）/ Tushare `fund_nav.accum_nav`。
  - `adj_nav`（后复权净值）：**临时回退 `adj_nav = acc_nav`**（累计净值已含分红累积，作近似后复权），标 `quality_flag="adj_nav_proxy"`（见 `domain/collect.py clean_nav`）；upsert 时 `adj_nav` 兜底非空（§2.20.2 NOT NULL）。
- **影响**：后复权净值非严格口径（E3）；回测/评分用 adj_nav 时需注意为近似值。
- **建议处置时点**：P1-01c/TP-04 回测引擎落地时，按 `fund_dividends` 分红明细计算真正后复权净值（删 DIVIDEND_MODE，E3 红线），替换回退。

---

## D7 · funds 表字段与技术规格§3.2 DDL 不一致

- **发现来源**：技术规格§3.2 `funds` DDL 含 `listing_board/scale/fee_rate/custodian/intraday_price/premium_discount`（DC-002 全类型/场内/折溢价），但详设§2.20.2 `funds` 表无这些字段。
- **性质**：两份设计文档口径不一致（详设§2.20.2 vs 技术规格§3.2）；按"详设+开发规范为准"原则，P0-04 以详设§2.20.2 建模。
- **当前处理**：P0-04 模型按详设§2.20.2（无上述字段）；P1-01a/b 适配器 `fetch_fund_list` 仅映射 `code/name/type_`。
- **影响**：DC-002 全类型/场内/折溢价功能（规模/费率/盘中价/折溢价）需补字段；不阻塞采集链路。
- **建议处置时点**：P1-02a/b（基金数据中心接口）落地 DC-002 全类型时，按技术规格§3.2 补字段迁移。

---

## D8 · empyrical 0.5 与 numpy 2.x 不兼容 + 因子命名口径冲突

- **发现来源**：P1-03a 落地时。① empyrical 0.5.0 的 `sortino_ratio` 用 `np.NINF`（numpy 2.0 已删，降级 AttributeError）；② 技术规格§3.3 `metrics.py` 用因子名 `return/risk/perf/scale/manager` + 旧权重 `0.30/0.25/0.20/0.15/0.10`，与详设§3.3.8.1（E4/E5 闭环，权威）+ CLAUDE.md §4 红线的 `ret/risk/perf/scale/manager` + `20/25/20/15/20` 冲突。
- **性质**：① 依赖兼容（empyrical 未适配 numpy 2.x）；② 文档口径（技术规格是 E4/E5 修订前基线，同 D3）。
- **当前处理**（P1-03a）：
  - sortino 自实现（`domain/metrics.py _sortino`，年化下行风险法），其余 empyrical 函数（annual_return/sharpe/max_drawdown/calmar/volatility）在 numpy 2 下正常。
  - 因子命名/权重**以详设§3.3.8.1 + CLAUDE.md §4 红线为准**（`ret/risk/perf/scale/manager`，20/25/20/15/20）；技术规格 metrics.py 旧口径属修订前基线，待 P1-03b 五因子合成时统一。
- **影响**：sortino 自实现非 empyrical 标准实现（语义一致，实现细节略异）；因子命名以红线为准。
- **建议处置时点**：empyrical 升级适配 numpy 2.x 后可换回 `ep.sortino_ratio`；技术规格§3.3 因子命名随 D3 一并修订。

---

*更新约定：每解决一项，在对应条目末尾追加 `已解决 @ <commit>` 并保留条目用于回溯。*

---

## D9 · NL 解析规则层未达 85% SLA(需 LLM 增强)

- **发现来源**：P1-06b 落地后跑 160 条评测集(nl_eval_set.json)。规则兜底层独立实现对结构化 100 条严格口径 82%，未达 §3.4.7 SLA≥85%。
- **性质**：就绪评估已知(规则层结构化 100% 是 nl_baseline 与评测集同源；独立实现口径略异)。生产解析器 = LLM + 规则 + 澄清，需 LLM 增强(C1 key)方达 85%。
- **当前处理**：P1-06b 交付规则兜底层(domain/nl_parse.py) + E6 红线(稳健排除 index/etf) + 端点(POST /api/screen/nl)；LLM 增强待 C1。
- **影响**：NL 选基在 LLM key 注入前准确率未达 SLA；规则层可用但需 LLM 增强。
- **建议处置时点**：C1 LLM key/供应商确认后，加 LLM 解析 + 规则兜底 + 澄清管线(对齐 TP-02 / nl_parse_LLM提示词设计稿)。
> ✅ **已解决 @ 5ab00c2**：P1-06b 落地 LLM 增强(rule fast-path + LLM + rule_normalize + clarify 管线) + 160 条评测门禁；用 DeepSeek key 实测合并 160 条 strict=0.90 ≥ 0.85 SLA。E6 口径裁决为 TYPE 约束(稳健->type∈[bond,mixed])。

---

*更新约定(续)*

---

## D10 · alembic 迁移链 autogenerate 重复建表（P0-04b）

- **发现来源**：P1-22 部署运行 `alembic upgrade head` 在干净库跑时。5 个 migration(`migrations/versions/*.py`)均用 `alembic revision --autogenerate` 生成，但生成时目标库缺前序迁移建的表，导致每个 migration 都重复 `create_table` 全部核心表(funds/navs/scores/paper_*/...)。第二个迁移起报 `DuplicateTable: relation "funds" already exists`。
- **性质**：迁移脚本缺陷（autogenerate 未考虑前序迁移已建表）。测试一直用 `Base.metadata.create_all`(conftest db_engine)从未端到端跑过 alembic，故未暴露。
- **当前处理**：P1-22 部署 migrate 改用 `scripts/init_db.py`(`Base.metadata.create_all`，与 ORM 模型/测试同口径，已验证建 14 表)兜底；compose migrate 服务不跑 `alembic upgrade head`。
- **影响**：干净库无法 `alembic upgrade head`；schema 演进(后续 alembic revision)受阻塞。
- **建议处置时点**：**P1-23 上线前**。重写迁移链：每个 migration 只建本任务新增表(admin_users/data_quality_log/fund_dividends/scheduler_jobs + initial_core)，或重生成单一干净 initial migration。详见 REVIEW_20260806 行动项 A1。
> ✅ **已解决 @ 2026-08-06（本轮）**：重写 4 个非初始 migration，使其只建本任务拥有的表（e2de76→admin_users / 2467→data_quality_log / 742d→fund_dividends / f3a1→scheduler_jobs+2 索引）；bb11 初始 10 核心表不变。`alembic upgrade head` 在干净 PG 库顺序通过（14 应用表 + alembic_version），`downgrade base` 与再 upgrade 均通过。逐列/逐索引比对迁移产物与 `create_all` 完全一致（0 drift）。`scripts/init_db.py` 改走 alembic（含历史 create_all 库 stamp 收编），compose migrate 服务回归迁移链。建表 DDL 交付文档见 `15_数据库DDL/`。

---

## 搁置项（SHELVED · 非业务，MVP 落地后重启）

> **决策（2026-08-07）**：优先业务功能、尽快推进 MVP 落地；以下非业务（运维/流程/基建）项暂时搁置，不阻塞 MVP 上线。来源：REVIEW_20260806 行动项 A3/A4/A5/A7/A8 的非业务部分 + P1-23 拆分。

| ID | 搁置项 | 性质 | 原计划 | 重启条件 |
|----|--------|------|--------|----------|
| S1 | §2.16 监控（Prometheus/指标/告警） | 运维 | P1-23 / A3 | MVP 灰度跑通后接 |
| S2 | §2.14 备份（PG 定时备份/恢复演练） | 运维 | P1-23 / A3 | MVP 上线后立即补（数据安全底线） |
| S3 | CR 流程（`13_需求变更管理规范/cr/` 目录+模板） | 流程 | A4 | 下一轮评审前建立 |
| S4 | CI PG service container（db 测试纳入 CI） | 基建 | A5 | CI 覆盖率口径需对齐时 |
| S5 | 全量镜像构建验证（`docker compose up -d --build` 端到端） | 基建 | A7 | 沙箱 PyPI 网络恢复后 |
| S6 | 后台 /monitor 端点（运维监控视图） | 运维 | A8 | S1 监控落地时 |
| S7 | 后台 /change-assessment 端点（变更评估视图） | 流程 | A8 | S3 CR 流程建立时 |

> **不搁置（业务/上线必做）**：A2 密钥轮换（安全，用户操作，公网上线前必做）、~~后台 /admin/jobs 端点（业务数据视图）~~ ✅已实现（2026-08-07，见 CHANGELOG / `api/v1/admin.py` `GET /admin/jobs` + `domain.scheduler.record_job_run` 落库 §3.14.3/§3.14.5）、/quality 端点（业务数据视图，仍待实现 P2-03c）、~~stylebox 风格箱算法（评估引擎业务）~~ ✅已实现（2026-08-07，见 CHANGELOG / `domain/stylebox.py`）、D6 adj_nav 真实复权（E3 业务正确性）、P1-23a 灰度上线本身。

---

## 解决状态汇总（2026-08-06 更新）

| 条目 | 状态 | 处置 | 关联 commit |
|------|------|------|-------------|
| D1 · navs 分区策略 | 📌 延期（非缺陷） | §2.20.2 DDL 注记，P1-22 落地 | - |
| D2 · 22 表字段 | 📌 延期（非缺陷） | §2.20.3 注记，各模块开工前补；admin_users/data_quality_log 已补 | - |
| D3 · 五因子口径冲突 | ✅ 已解决 | 详设 §2.20.2/§2.21.2 统一新口径 `ret/risk/perf/scale/manager` | 7612a5e |
| D4 · 信封字段/路径不一致 | ✅ 已解决 | CLAUDE.md §6 + 开发规范 §6.2 补 `disclaimer`（7 字段）；§3 路径已由远程修正 | 7612a5e |
| D5 · 宿主端口避让 | 📌 环境事实已处理 | docker-compose 端口避让，无仓库变更 | - |
| D6 · acc_nav/adj_nav 口径 | 🔄 部分解决 | acc_nav 已补(P1-01c)；adj_nav 临时回退 acc_nav，待 TP-04 分红复权 | P1-01c |
| D7 · funds 表字段不一致 | 📌 延期 | 按详设§2.20.2 建模；DC-002 全类型待 P1-02 补字段 | - |
| D8 · empyrical/numpy兼容+因子命名 | 🔄 部分解决 | sortino 自实现；因子命名以红线为准，待 P1-03b 统一 | P1-03a |
| D9 · NL 规则层未达 85% SLA | ✅ 已解决 | P1-06b LLM+规则+澄清管线，160 条 strict=0.90≥0.85；E6 裁决=TYPE 约束 | 5ab00c2 |
| D10 · alembic 迁移链 autogenerate 重复建表 | ✅ 已解决 | 重写 4 迁移各只建本表；alembic upgrade head 干净库通过；与 create_all 0 drift；init_db.py 改走 alembic+stamp 收编 | 本轮 |

> 注：本文件原以非 UTF-8 编码入库，本次重写为标准 UTF-8。
