# CHANGELOG · FundLens

遵循 [Keep a Changelog](https://keepachangelog.com/)，按版本记录 Added/Changed/Fixed。

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

### Fixed
- review 修复 /score 恒 None + attribution 误导 0 + 闰年崩溃（`4cfe299`）
- upsert_funds 分批（PG 参数上限 65535，`5937f35`）
- P1-06b E6 排除用 not_in 完整排除 index/etf（`d990dfe`）

### Known Issues (DEFERRED)
- D6 adj_nav 临时回退 acc_nav（待真实复权，E3 近似）
- D9 NL 规则层 82% 未达 85% SLA（待 LLM key C1）
- D1/D2/D5/D7 延期项（不阻塞 Phase 1 主干）
