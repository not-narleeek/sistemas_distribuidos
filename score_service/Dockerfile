FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY score_service.py .

ENTRYPOINT ["python", "score_service.py"]
