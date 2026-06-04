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

EXPOSE 8000

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
