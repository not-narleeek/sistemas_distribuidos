FROM python:3.10-slim

WORKDIR /cache

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cache.py .

ENTRYPOINT ["python", "cache.py"]
