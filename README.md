# FundLens · 基金评估与模拟交易系统

> 面向**个人投资者 / 学习者**的 Python 全栈基金评估与模拟交易系统，覆盖"学 -> 懂 -> 筛 -> 练 -> 评 -> 穿"12 个功能模块。MVP 阶段为单用户，不做实盘下单执行。

当前处于 **Phase 0 工程骨架**（仓库 / docker-compose / CI / 响应信封 / 结构化日志 / Streamlit 壳）。业务算法与接口将在 Phase 1 逐步落地。

---

## 技术栈（详设 §2.7，禁止擅自更换）

| 层 | 选型 |
|----|------|
| 运行时 | Python 3.11 |
| 内部 API | FastAPI 0.110+ |
| 前端 | Streamlit 1.35+（纯 Python，不引入 TS/JS 工程） |
| 存储 | PostgreSQL 15 + Redis 7（ADR-003/004） |
| ORM | SQLAlchemy 2.x + Alembic |
| 算法 | pandas / empyrical / vectorbt / statsmodels |
| AI | LangChain + Chroma + 低价 LLM（DeepSeek / 通义千问） |
| 数据采集 | AkShare（主）+ Tushare（备），须有 fallback（§2.15） |

---

## 目录结构（开发规范 §2）

```
api/           FastAPI 入口（路由/校验/依赖注入；main.py 装配全局 handler 与中间件）
domain/        领域与算法（纯逻辑，不依赖 Web；P1-03* 评分/归因/回测/宏观/筛选）
schemas/       Pydantic 契约（envelope.py 七字段信封 §2.21；errors.py 错误码 §4.2）
infra/         基础设施（logging/middleware/db/redis/external/lock）
workers/       后台进程入口（collect/batch/weekly，详设 §3.14）
config/        配置加载（pydantic-settings，§9.1 外部化）
app/           Streamlit 前端（app.py 壳 + pages/12 页 + components + api_client）
tests/         单测/集成
docs/基金评估系统_交付文档/   全部交付文档（需求/设计/TP/规范/计划）
```

---

## 快速启动

### 一键 Docker（推荐）

```bash
cp .env.example .env          # 占位配置（密钥勿入库）
docker compose up -d          # 起 postgres/redis/api/worker/streamlit
# API:       http://localhost:18000  (健康: /api/v1/health, 文档: /api/docs)
# Streamlit: http://localhost:18501
# Postgres:  localhost:15432  (fundlens/changeme)
# Redis:     localhost:16379
```

> 宿主端口已避让既有占用（API 18000 / Streamlit 18501 / PG 15432 / Redis 16379）；容器内部仍用标准端口，服务间通过 compose 服务名互联。本地非 docker 开发（`uvicorn` / `streamlit run`）仍用 8000 / 8501 默认端口。

### 本地开发

```bash
python3.11 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

uvicorn api.main:app --reload          # 内部 API
streamlit run app/app.py              # 前端
python -m workers.collect              # 采集 worker（占位）
```

---

## 质量门禁（开发规范 §1.3 / §11）

```bash
make check      # ruff + mypy + pytest(coverage)
# 或分步：
ruff check . && black --check . && isort --check .
mypy .
pytest --cov=domain --cov=schemas --cov=api
```

- 格式 `black`（行宽 100）+ `isort`；Lint `ruff`；类型 `mypy --strict`；测试 `pytest`。
- 统一响应信封七字段：`{code, data, source, as_of, disclaimer, message, trace_id}`（§2.21.1）。
- 错误码区间 `400xx/401xx/403xx/429xx/500xx/503xx`（§4.2），新增须在体系内扩段。

提交规范：[Conventional Commits](https://www.conventionalcommits.org/)，关联 `FR-xx/DC-xxx`；PR ≥ 1 评审、CI 全绿方可合并。详见 `docs/基金评估系统_交付文档/11_开发规范/`。

---

## 文档地图

全部设计文档位于 `docs/基金评估系统_交付文档/`（BRD v1.2 / 技术规格 v1.3 / 详细设计 v1.1 / TP-01~06 / 开发规范 v1.0 / 开发任务分解 v1.1 / 编码就绪评估）。编码前必读对应模块文档并在代码注释中引用，详见根目录 `CLAUDE.md`。

---

> 免责声明：本系统仅供参考，不构成投资建议（详细设计 §5.2）。
