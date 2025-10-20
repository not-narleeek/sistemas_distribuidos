FROM python:3.10-slim

WORKDIR /app

COPY storage_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common /app/common
COPY storage_service/storage_service.py /app/storage_service.py

ENV PYTHONPATH=/app:/app/common

ENTRYPOINT ["python", "storage_service.py"]
