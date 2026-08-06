# FundLens 数据库建表 DDL（交付文档）

> **文档定位**：FundLens 全部数据库表的建表 DDL，作为项目交付与运维建库的权威依据。
> **生成方式**：由 alembic 迁移链 `alembic upgrade head --sql` 离线生成（PostgreSQL 方言），逐表/逐索引与 ORM 模型 `Base.metadata.create_all` 产物比对一致（0 drift，见 §5）。
> **配套文件**：`schema.sql`（同目录，仅 CREATE 语句，可直接 `psql -f schema.sql` 应用）。
> **相关文档**：详细设计 §2.20（DB schema）/§2.19.6/§3.1.4/§3.5.4/§3.14.3；P0-04b 迁移链修复见 `REVIEW_20260806` 行动项 A1 / `DEFERRED.md` D10。

---

## 0. 概述

| 项 | 值 |
|----|----|
| 数据库 | PostgreSQL（ADR-003 三层存储；ADR-004 多副本） |
| 应用表数 | **14**（10 核心表 + admin_users + data_quality_log + fund_dividends + scheduler_jobs） |
| 索引数 | 5（显式 `CREATE INDEX`；不含主键/唯一约束自动索引） |
| schema 真相源 | ORM 模型 `infra/db/models/*.py`（SQLAlchemy 2.0 Mapped 风格） |
| 建库路径 | 部署走 `alembic upgrade head`（经 `scripts/init_db.py`，含历史 create_all 库 stamp 收编）；测试走 `conftest` 的 `Base.metadata.create_all`（隔离建表） |
| 字符集/时区 | UTF-8；时间戳一律 `TIMESTAMP WITH TIME ZONE`（`server_default=now()`） |

**关键约束口径**（CLAUDE.md §4 红线在 schema 层的落点）：
- `scores.weights`/`scores.factors` 为 **JSONB**（五因子结构，TP-01 §3.1；E4/E5）。
- `navs.adj_nav` 后复权净值非空（E3；`acc_nav` 可空，`adj_nav` MVP 暂回退 `acc_nav`，见 D6）。
- `paper_trades.side` CHECK ∈ ('buy','sell')；`portfolios.source` CHECK ∈ ('template','manual','import')。
- `fund_dividends`（P1-07b / E3）为分红复权数据源。
- `scheduler_jobs.args`/`result_summary` 为 JSONB（§3.14.3）。

---

## 1. 迁移链（alembic，线性单链）

> P0-04b 修复后，每个迁移只建本任务新增表（不再重复建已存在表），`alembic upgrade head` 在干净库顺序通过。

| 顺序 | Revision | 任务 / 模块 | 新增表 | 详设引用 |
|------|----------|------------|--------|----------|
| 1 | `bb11c89a96bd` | P0-04a 初始核心表 | funds / paper_accounts / holdings / navs / paper_positions / paper_trades / portfolios / research_metrics / scores / portfolio_weights（10） | §2.20.2 |
| 2 | `e2de76ea9934` | P0-05 后台鉴权 | admin_users | §2.19.6 |
| 3 | `2467f55bb86e` | P1-01c 数据质量 | data_quality_log | §3.1.4 |
| 4 | `742d963668ac` | P1-07b 分红复权(E3) | fund_dividends | §3.5.4 |
| 5 | `f3a1c90e4b2d`(head) | P1-10b 调度历史 | scheduler_jobs | §3.14.3 |

alembic 自管表 `alembic_version(version_num VARCHAR(32) PK)` 记录当前 head，非应用表。

---

## 2. DDL 清单（按迁移/任务分组）

### 2.1 P0-04a 初始核心表（bb11c89a96bd，§2.20.2）

#### funds — 基金主数据

```sql
CREATE TABLE funds (
    code VARCHAR(12) NOT NULL,
    name VARCHAR(64) NOT NULL,
    type VARCHAR(16) NOT NULL,
    sub_type VARCHAR(32),
    theme VARCHAR(32),
    style VARCHAR(16),
    launch_date DATE,
    source VARCHAR(32) NOT NULL,
    as_of DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (code)
);
CREATE INDEX ix_funds_type_theme ON funds (type, theme);
```

#### paper_accounts — 模拟交易账户（§3.5）

```sql
CREATE TABLE paper_accounts (
    account_id VARCHAR(32) NOT NULL,
    init_capital NUMERIC(18, 2) DEFAULT 1000000 NOT NULL,
    cash NUMERIC(18, 2) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (account_id)
);
```

#### holdings — 基金持仓穿透（§3.9）

```sql
CREATE TABLE holdings (
    code VARCHAR(12) NOT NULL,
    report_date DATE NOT NULL,
    stock_code VARCHAR(12) NOT NULL,
    stock_name VARCHAR(64),
    weight NUMERIC(12, 6),
    source VARCHAR(32) NOT NULL,
    as_of DATE NOT NULL,
    PRIMARY KEY (code, report_date, stock_code),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
```

#### navs — 基金净值（§3.2；E3 后复权）

```sql
CREATE TABLE navs (
    code VARCHAR(12) NOT NULL,
    trade_date DATE NOT NULL,
    nav NUMERIC(18, 4) NOT NULL,
    acc_nav NUMERIC(18, 4),
    adj_nav NUMERIC(18, 4) NOT NULL,
    is_estimate BOOLEAN DEFAULT false NOT NULL,
    source VARCHAR(32) NOT NULL,
    as_of DATE NOT NULL,
    PRIMARY KEY (code, trade_date),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
CREATE INDEX ix_navs_date ON navs (trade_date);
```

#### paper_positions — 模拟持仓（§3.5）

```sql
CREATE TABLE paper_positions (
    account_id VARCHAR(32) NOT NULL,
    code VARCHAR(12) NOT NULL,
    shares NUMERIC(18, 4) NOT NULL,
    cost NUMERIC(18, 4) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (account_id, code),
    FOREIGN KEY(account_id) REFERENCES paper_accounts (account_id) ON DELETE CASCADE,
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
```

#### paper_trades — 模拟交易流水（§3.5）

```sql
CREATE TABLE paper_trades (
    trade_id BIGSERIAL NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    code VARCHAR(12) NOT NULL,
    side VARCHAR(4) NOT NULL,
    shares NUMERIC(18, 4) NOT NULL,
    nav NUMERIC(18, 4) NOT NULL,
    trade_date DATE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (trade_id),
    CONSTRAINT ck_paper_trades_side CHECK (side IN ('buy','sell')),
    FOREIGN KEY(account_id) REFERENCES paper_accounts (account_id) ON DELETE CASCADE,
    FOREIGN KEY(code) REFERENCES funds (code)
);
CREATE INDEX ix_trades_account ON paper_trades (account_id, trade_date);
```

#### portfolios — 组合（§3.6）

```sql
CREATE TABLE portfolios (
    portfolio_id VARCHAR(32) NOT NULL,
    account_id VARCHAR(32) NOT NULL,
    name VARCHAR(64),
    source VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (portfolio_id),
    CONSTRAINT ck_portfolios_source CHECK (source IN ('template','manual','import')),
    FOREIGN KEY(account_id) REFERENCES paper_accounts (account_id) ON DELETE CASCADE
);
```

#### research_metrics — 研究指标（PEG/ERP，§3.8；E7/E10/E11）

```sql
CREATE TABLE research_metrics (
    code VARCHAR(12) NOT NULL,
    alpha NUMERIC(12, 6),
    beta NUMERIC(12, 6),
    tracking_error NUMERIC(12, 6),
    info_ratio NUMERIC(12, 6),
    peg NUMERIC(12, 6),
    erp NUMERIC(12, 6),
    peg_available BOOLEAN DEFAULT false NOT NULL,
    erp_available BOOLEAN DEFAULT false NOT NULL,
    cv_flag BOOLEAN DEFAULT false NOT NULL,
    as_of DATE NOT NULL,
    PRIMARY KEY (code),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
```

#### scores — 五因子评分（§3.3；E4/E5，TP-01 §3.1）

```sql
CREATE TABLE scores (
    code VARCHAR(12) NOT NULL,
    "window" VARCHAR(8) DEFAULT '3y' NOT NULL,
    weights JSONB NOT NULL,
    composite NUMERIC(8, 4) NOT NULL,
    factors JSONB NOT NULL,
    as_of DATE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (code),
    FOREIGN KEY(code) REFERENCES funds (code) ON DELETE CASCADE
);
```

#### portfolio_weights — 组合权重（§3.6）

```sql
CREATE TABLE portfolio_weights (
    portfolio_id VARCHAR(32) NOT NULL,
    code VARCHAR(12) NOT NULL,
    weight NUMERIC(8, 4) NOT NULL,
    PRIMARY KEY (portfolio_id, code),
    FOREIGN KEY(code) REFERENCES funds (code),
    FOREIGN KEY(portfolio_id) REFERENCES portfolios (portfolio_id) ON DELETE CASCADE
);
```

### 2.2 P0-05 admin_users — 后台用户（e2de76ea9934，§2.19.6）

```sql
CREATE TABLE admin_users (
    id BIGSERIAL NOT NULL,
    username VARCHAR(64) NOT NULL,
    password_encrypted VARCHAR(256) NOT NULL,
    must_change_password BOOLEAN DEFAULT true NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (username)
);
```

### 2.3 P1-01c data_quality_log — 数据质量日志（2467f55bb86e，§3.1.4）

```sql
CREATE TABLE data_quality_log (
    id BIGSERIAL NOT NULL,
    entity VARCHAR(32),
    check_date DATE,
    missing_count INTEGER,
    anomaly_flag BOOLEAN,
    cv_error NUMERIC(8, 4),
    source VARCHAR(32),
    as_of DATE,
    note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);
```

### 2.4 P1-07b fund_dividends — 基金分红（742d963668ac，§3.5.4 / E3）

```sql
CREATE TABLE fund_dividends (
    code VARCHAR(12) NOT NULL,
    ex_date DATE NOT NULL,
    div_per_unit NUMERIC(10, 6),
    source VARCHAR(32),
    PRIMARY KEY (code, ex_date)
);
```

### 2.5 P1-10b scheduler_jobs — 调度任务执行历史（f3a1c90e4b2d，§3.14.3）

```sql
CREATE TABLE scheduler_jobs (
    id BIGSERIAL NOT NULL,
    job_id VARCHAR(64) NOT NULL,
    job_name VARCHAR(128),
    trigger VARCHAR(16) NOT NULL,
    status VARCHAR(16) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    finished_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    error TEXT,
    args JSONB,
    result_summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
    PRIMARY KEY (id)
);
CREATE INDEX ix_scheduler_jobs_job_id ON scheduler_jobs (job_id);
CREATE INDEX ix_scheduler_jobs_status ON scheduler_jobs (status);
```

> 注：`trigger`/`status` 的默认值由 ORM Python 侧 `default=` 提供（`infra/db/models/scheduler.py`），DB 层无 `server_default`，迁移与 create_all 产物一致。

---

## 3. 索引清单

| 索引名 | 表 | 列 | 所属迁移 |
|--------|----|----|----------|
| ix_funds_type_theme | funds | (type, theme) | bb11 |
| ix_navs_date | navs | (trade_date) | bb11 |
| ix_trades_account | paper_trades | (account_id, trade_date) | bb11 |
| ix_scheduler_jobs_job_id | scheduler_jobs | (job_id) | f3a1 |
| ix_scheduler_jobs_status | scheduler_jobs | (status) | f3a1 |

> 主键（PRIMARY KEY）与唯一约束（UNIQUE）自动创建索引，未列入上表。

---

## 4. 外键关系图

```
funds (PK: code)
 ├── holdings.code        ON DELETE CASCADE
 ├── navs.code            ON DELETE CASCADE
 ├── paper_positions.code ON DELETE CASCADE
 ├── paper_trades.code    (无级联)
 ├── research_metrics.code ON DELETE CASCADE
 ├── scores.code          ON DELETE CASCADE
 └── portfolio_weights.code (无级联)

paper_accounts (PK: account_id)
 ├── paper_positions.account_id ON DELETE CASCADE
 ├── paper_trades.account_id    ON DELETE CASCADE
 └── portfolios.account_id      ON DELETE CASCADE

portfolios (PK: portfolio_id)
 └── portfolio_weights.portfolio_id ON DELETE CASCADE
```

---

## 5. 验证记录（2026-08-06）

| 检查项 | 方法 | 结果 |
|--------|------|------|
| 干净库 `alembic upgrade head` | 空 PG 库顺序应用 5 迁移 | ✅ 14 应用表 + alembic_version，无 DuplicateTable |
| `downgrade base` | 反向回滚 | ✅ 全部 drop |
| 再 `upgrade head` | 幂等性 | ✅ 重建 14 表 |
| **迁移 vs create_all 逐列比对** | `information_schema.columns` diff | ✅ **0 drift**（94 列全一致） |
| **迁移 vs create_all 逐索引比对** | `pg_indexes` diff | ✅ **0 drift**（5 索引全一致） |
| `init_db.py` stamp 收编 | 历史 create_all 库(14 表无 alembic_version) | ✅ stamp head，采纳现有 schema |
| `init_db.py` 幂等 | head 库再跑 | ✅ no-op |
| 质量门禁 | black/ruff/mypy on migrations | ✅ 0 error / 0 issue |

**结论**：迁移链与 ORM 模型 create_all 产物完全等价；部署走 alembic、测试走 create_all，两侧 schema 一致，可安全推进 P1-23 上线。

---

## 6. 变更与演进

- **新增表/字段**：走 `alembic revision --autogenerate -m "..."` 生成增量迁移（只含本变更），不再全表重建。
- **本 DDL 文档维护**：迁移链变更后重新执行 `alembic upgrade head --sql` 并同步更新本文件与 `schema.sql`。
- **历史**：本 DDL 由 P0-04b 迁移链修复（2026-08-06）后的迁移链产出；修复前的迁移链因 autogenerate 重复建表而无法在干净库 `upgrade head`。

---

*本文件随迁移链演进同步；schema 真相源为 `infra/db/models/*.py` ORM 模型，DDL 为其 PostgreSQL 物化产物。*
