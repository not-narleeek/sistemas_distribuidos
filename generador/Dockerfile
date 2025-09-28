FROM python:3.10-slim

WORKDIR /generador

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generador_yahoo.py .

ENTRYPOINT ["python", "generador_yahoo.py"]
