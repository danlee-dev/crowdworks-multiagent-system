# 베이스 이미지는 Python 3.11 slim
FROM mcr.microsoft.com/playwright/python:latest

# 작업 디렉터리를 /app 으로 설정
WORKDIR /app

# 의존성 파일 복사 및 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 스크립트 모두 복사
COPY . .

# 기본 진입점(override 가능)
CMD ["python"]
