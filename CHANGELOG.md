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

### Fixed
- review 修复 /score 恒 None + attribution 误导 0 + 闰年崩溃（`4cfe299`）
- upsert_funds 分批（PG 参数上限 65535，`5937f35`）
- P1-06b E6 排除用 not_in 完整排除 index/etf（`d990dfe`）

### Known Issues (DEFERRED)
- D6 adj_nav 临时回退 acc_nav（待真实复权，E3 近似）
- D9 NL 规则层 82% 未达 85% SLA（待 LLM key C1）
- D1/D2/D5/D7 延期项（不阻塞 Phase 1 主干）
