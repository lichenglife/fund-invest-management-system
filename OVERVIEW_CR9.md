# CR-20260806-01 前端改造 · #9 响应式移动优先与可访问性逐页落地

> 分支：`feature/cr-20260806-01-frontend-overhaul` · 接续 #7 令牌 v2 地基、#8 逐页着色收敛

## 一、本次交付内容

### 1. 响应式基础设施（全局，覆盖全部 12 个页面）
- **视口桥** `ui.inject_responsive_bridge()`：注入一段轻量 JS，将当前视口宽度写到
  `<html data-fl-view>`（值：`sm` ≤640 / `md` ≤900 / `lg`），驱动纯 CSS 响应式，
  Python 侧无需感知屏幕宽度。`inject_global_style()` 每页调用一次，自动生效。
- **全局移动端堆叠**：`style.css` 新增 `[data-fl-view="sm"]` 规则，手机端将**所有**
  `st.columns` 容器强制 `flex-wrap` 并子列 `flex:1 1 100%`，即任意页面的多列布局在
  手机上自动堆叠为单列；`md`（平板）仅收紧列间距，保留原有 [3,2] 等布局意图。
- **响应式网格** `.fl-grid`：`display:grid; grid-template-columns: repeat(auto-fit,
  minmax(var(--fl-min,200px),1fr))`，宽度自适应回流，无需手写断点。

### 2. 可访问性（A11y · AA，逐页落地）
- `ui.page_header()` 现于每个页面顶部注入：
  - 「跳到主内容」跳转链接（`.fl-skip-link`，键盘聚焦时显形）；
  - `<div id="main-content" tabindex="-1" role="main">` 无障碍地标，作为跳转目标；
  - 跳转目标聚焦时不显示焦点环（`#main-content:focus{outline:none}`）。
- 既有 AA 基线延续：`:focus-visible` 焦点环、`prefers-reduced-motion` 减弱动效、
  `.fl-sr-only` 屏幕阅读器专用。

### 3. 组件与页面改造
- `kpi_card.py`：抽离 `kpi_card_html()`（返回可拼接的 KPI 卡 HTML 字符串），
  `kpi_card()` 改为调用它；`__all__` 导出 `kpi_card_html`。
- `ui.py`：新增 `kpi_grid(cards, min_col_width=200)`（在单个 `.fl-grid` 容器内拼接多卡，
  自动回流）；新增 `inject_responsive_bridge()`；`inject_global_style()` 末尾调用桥；
  `page_header()` 注入跳转链接 + 地标；`__all__` 增补两项。
- **01_仪表盘**：两张 KPI 卡由 `st.columns(2)`+`kpi_card` 循环改为 `kpi_grid(...)`。
- **13_后台管理**：「今日执行概览」4 张 KPI 卡由 `st.columns(4)` 改为 `ui.kpi_grid(...)`。
  （监控 Tab 内的 `st.columns(2)` 监控项因含额外 `st.markdown` 说明，保留原结构，
  仍由全局 `sm` 堆叠规则覆盖移动端。）

### 4. 测试
- `tests/test_frontend_tokens.py` 由 6 项扩至 **10 项**，新增：
  - `test_a11y_skip_link_and_focus_ring`（跳转链接/焦点可见/减弱动效）；
  - `test_responsive_grid_and_viewport_bridge`（`.fl-grid`/auto-fit/`[data-fl-view="sm"]`/`#main-content`）；
  - `test_ui_responsive_infra_present`（ui 导出视口桥+网格、表头注入跳转链接+地标）；
  - `test_kpi_card_html_exported`（kpi_card_html 抽离并产出 `fl-kpi-card`）。
  - 全部测试 Streamlit-free（读源码/CSS 文本断言），沙箱内可直接运行。

## 二、验证
- `py_compile` 改动文件（ui.py / kpi_card.py / 01 / 13 / test）全绿。
- 令牌测试 **10/10 通过**（含 1 项 `test_no_inline_hex_outside_utils` 锁死游离硬色码，
  确认 #9 新增代码无游离 `#xxxxxx`）。

## 三、范围说明（透明）
- 本次对 KPI/指标卡网格做了**显性** `kpi_grid` 落地的页面：01、13。
- 其余页面（03/05/07/08/12 等的列布局）由全局 `[data-fl-view="sm"]` 堆叠规则统一覆盖
  移动端单列，无需逐页改代码；如需将这些页面的指标卡也改 `kpi_grid` 以获得平板 2 列级
  精细回流，可后续在 #11 或独立 refinement 中补做（视觉回归需人工在浏览器确认）。
- 因沙箱无法渲染 Streamlit，响应式/跳转链接的最终观感需在浏览器实机确认。

## 四、下一步
- #10 部署交付口径与前后端联调
- #11 前端测试纳入 CI 并关闭 CR（含 `make check` 接入、文案/免责/角色文案收尾、提交+PR 关联 `Closes CR-20260806-01`）
