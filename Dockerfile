FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app


COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


RUN playwright install chromium


COPY . .


CMD ["python", "app/main.py"]
