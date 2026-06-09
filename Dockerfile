# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY arin_lookup.py .
COPY app ./app
COPY scripts ./scripts
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

# 构建阶段验证依赖与应用可导入，避免运行时才暴露 ModuleNotFoundError
# Verify imports without requiring a live database at build time
RUN python -c "from app.agent_chat import agent_chat_stream; from app.database import init_db; print('app import ok')"

USER appuser
EXPOSE 8000

# --proxy-headers：配合 HTTPS 反向代理时取真实客户端 IP/协议；
# 需信任的代理地址通过 FORWARDED_ALLOW_IPS 环境变量配置（uvicorn 原生支持）。
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers
