FROM python:3.10-slim

# 환경 변수 설정 - 출력 버퍼링 비활성화
ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=utf-8

# PostgreSQL 클라이언트 및 개발 라이브러리, WeasyPrint 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install --with-deps

COPY app/ ./app/

COPY .env* ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
