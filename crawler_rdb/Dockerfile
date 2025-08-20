# crawler_rdb/Dockerfile
FROM python:3.10-slim

# 시스템 패키지 설치 (psycopg2 빌드용)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉터리
WORKDIR /app

# 의존성 설치
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 기본 실행 커맨드
CMD ["bash", "-lc", "python3 -B main.py --crawler kamis-latest"]