FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8000

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY arin_lookup.py .
COPY app ./app
COPY scripts ./scripts
RUN mkdir -p /app/data

# 构建阶段验证依赖与应用可导入，避免运行时才暴露 ModuleNotFoundError
# Verify imports without requiring a live database at build time
RUN python -c "from app.agent_chat import agent_chat_stream; from app.database import init_db; print('app import ok')"

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
