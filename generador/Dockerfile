FROM python:3.10-slim

WORKDIR /app

COPY generador/requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6-dev \
        libpng-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY common /app/common
COPY generador/generador_yahoo.py /app/generador_yahoo.py

ENV PYTHONPATH=/app:/app/common

ENTRYPOINT ["python", "generador_yahoo.py"]
