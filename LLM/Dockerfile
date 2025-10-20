FROM python:3.10-slim

WORKDIR /app

COPY LLM/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY common /app/common
COPY LLM/kafka_llm_consumer.py /app/kafka_llm_consumer.py

ENV PYTHONPATH=/app:/app/common

ENTRYPOINT ["python", "kafka_llm_consumer.py"]
