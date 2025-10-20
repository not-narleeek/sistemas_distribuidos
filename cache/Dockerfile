FROM python:3.10-slim

WORKDIR /app

COPY cache/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common /app/common
COPY cache/cache.py /app/cache.py

ENV PYTHONPATH=/app:/app/common

ENTRYPOINT ["python", "cache.py"]
