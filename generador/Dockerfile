FROM python:3.10-slim

WORKDIR /generador

COPY requirements.txt .
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6-dev \
        libpng-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt

COPY generador_yahoo.py .

ENTRYPOINT ["python", "generador_yahoo.py"]
