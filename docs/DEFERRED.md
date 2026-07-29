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

*更新约定：每解决一项，在对应条目末尾追加 `已解决 @ <commit>` 并保留条目用于回溯。*

---

## 解决状态汇总（2025-07-29 更新）

| 条目 | 状态 | 处置 | 关联 commit |
|------|------|------|-------------|
| D1 · navs 分区策略 | 📌 延期（非缺陷） | §2.20.2 DDL 注记，P1-22 落地 | - |
| D2 · 22 表字段 | 📌 延期（非缺陷） | §2.20.3 注记，各模块开工前补；admin_users/data_quality_log 已补 | - |
| D3 · 五因子口径冲突 | ✅ 已解决 | 详设 §2.20.2/§2.21.2 统一新口径 `ret/risk/perf/scale/manager` | 7612a5e |
| D4 · 信封字段/路径不一致 | ✅ 已解决 | CLAUDE.md §6 + 开发规范 §6.2 补 `disclaimer`（7 字段）；§3 路径已由远程修正 | 7612a5e |
| D5 · 宿主端口避让 | 📌 环境事实已处理 | docker-compose 端口避让，无仓库变更 | - |
| D6 · acc_nav/adj_nav 口径 | 🔄 部分解决 | acc_nav 已补(P1-01c)；adj_nav 临时回退 acc_nav，待 TP-04 分红复权 | P1-01c |
| D7 · funds 表字段不一致 | 📌 延期 | 按详设§2.20.2 建模；DC-002 全类型待 P1-02 补字段 | - |

> 注：本文件原以非 UTF-8 编码入库，本次重写为标准 UTF-8。
