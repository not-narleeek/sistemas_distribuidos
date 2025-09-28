FROM python:3.10-slim

WORKDIR /LLM

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY dummy_LLM.py .

CMD ["python", "dummy_LLM.py"]
