# Canalización batch Hadoop + Pig

Esta carpeta contiene el flujo batch solicitado en Tarea 3. Sigue los pasos resumidos para ejecutar el análisis o reproducir los experimentos.

## Prerrequisitos rápidos

```bash
# Verifica dependencias básicas
docker version
make --version
python --version
```

## Flujo Yahoo vs LLM (WordCount)

1. Arranca el clúster:
   ```bash
   make up
   ```
2. Prepara HDFS y publica stopwords:
   ```bash
   make hdfs-init
   ```
3. Exporta y sube datos (auto-detecta esquema; añade `SCHEMA=traffic` y parámetros de tráfico si es necesario):
   ```bash
   make load-data DUMP_PATH=/ruta/a/datos.csv
   ```
4. Ejecuta los jobs de Pig (Yahoo, LLM y comparador):
   ```bash
   make run-batch
   ```
5. Descarga resultados desde HDFS:
   ```bash
   make fetch
   ```
6. Genera tablas/Top-N opcionales:
   ```bash
   make compare [CHART=1]
   ```
7. Calcula métricas agregadas:
   ```bash
   make metrics
   ```
8. Apaga el entorno cuando finalices:
   ```bash
   make down
   ```

## Flujo de tráfico (FIFO/LFU/LRU)

1. Descubre archivos disponibles y crea el manifest:
   ```bash
   make discover-traffic [BASE_DIR=data_collected/traffic]
   ```
2. Normaliza los CSV crudos:
   ```bash
   make normalize-traffic [OVERWRITE=1]
   ```
3. Publica los datasets normalizados en HDFS:
   ```bash
   make hdfs-put-traffic
   ```
4. Ejecuta Pig para cada combinación política/distribución:
   ```bash
   make traffic-analysis
   ```
5. Trae los TSV al host:
   ```bash
   make fetch-traffic
   ```
6. Produce la comparativa global:
   ```bash
   make compare-traffic
   ```
7. Lanza todo el pipeline anterior en un solo comando si prefieres:
   ```bash
   make traffic-pipeline
   ```

## Utilidades adicionales

- Exportar desde MongoDB y subir directo a HDFS:
  ```bash
  python distributed-batch-ling/ingestion/exporter.py \
    --mongo-uri "mongodb://usuario:pwd@localhost:27017" \
    --mongo-db respuestas \
    --mongo-collection historico \
    --output-dir distributed-batch-ling/ingestion/output \
    --compose-file distributed-batch-ling/deploy/docker-compose.yml \
    --hdfs-base /data/input
  ```
- Limpiar artefactos y logs antes de nuevas corridas:
  ```bash
  make clean-artifacts
  make clean-logs
  ```
