# Dockerfile · FundLens（api / worker / streamlit 共用镜像，命令随 service 变）
# 对齐详设§2.7 Python 3.11 + §2.13 运行环境。

FROM python:3.11-slim AS base

# 运行时系统依赖（psycopg[binary] 自带 libpq，此处仅装最小运行时）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# 依赖先行（利用层缓存）
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-dev.txt

# 应用代码
COPY . .

EXPOSE 8000 8501

# 默认启动 API；worker / streamlit 由 compose 覆盖 command
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
