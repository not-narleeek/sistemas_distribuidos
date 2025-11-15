# Canalización batch Hadoop + Pig

Este módulo contiene todos los artefactos necesarios para ejecutar la Tarea 3 del curso: un análisis batch de respuestas humanas vs. respuestas generadas por el LLM.

## Estructura

```
ingestion/                # Exportador desde CSV/Parquet o MongoDB hacia CSV particionados
pig/                      # Scripts Pig + stopwords y UDFs Jython
pig/udf/text_utils.py     # Normalización y filtrado de tokens
pig/wordfreq.pig          # Trabajo MapReduce parametrizable (Yahoo / LLM)
pig/compare.pig           # Comparativa de frecuencias
deploy/docker-compose.yml # Clúster Hadoop (NameNode, DataNode, HistoryServer, Pig)
deploy/hadoop/Dockerfile  # Imagen Pig con Pig 0.17 y configs montadas
artifacts/                # Resultados traídos desde HDFS (poblado con `make fetch`)
logs/                     # Logs de Pig y Hadoop montados como volumen
scripts/metrics.py        # Cálculo de métricas (duración, throughput, tamaños)
```

## Prerrequisitos

- Docker Engine ≥ 20.10 con soporte `docker compose` v2.
- GNU Make, Python 3.10+.
- Archivo CSV/Parquet o acceso a MongoDB con columnas: `id_pregunta`, `respuesta_texto`, `origen`, `ts_creacion`.
- Conexión a Internet la primera vez (descarga Pig 0.17.0).

## Flujo típico

```bash
# 1) Levantar Hadoop + Pig
make up

# 2) Crear carpetas en HDFS
make hdfs-init

# 3) Exportar e ingerir datos desde CSV
make load-data DUMP_PATH=data/respuestas.csv

# 4) Ejecutar análisis completo (WordCount + comparativa)
make run-batch

# 5) Traer resultados a ./distributed-batch-ling/artifacts
make fetch

# 6) Generar tablas Top-N y gráficos
make compare CHART=1

# 7) Calcular métricas
make metrics
```

Los comandos `run-yahoo`, `run-llm` y `run-compare` también pueden invocarse de forma independiente.

## Exportación desde MongoDB

```bash
python distributed-batch-ling/ingestion/exporter.py \
  --mongo-uri "mongodb://usuario:pwd@localhost:27017" \
  --mongo-db respuestas \
  --mongo-collection historico \
  --output-dir distributed-batch-ling/ingestion/output \
  --verbose
```

El exportador genera tanto CSVs con metadatos (`*_respuestas.csv`) como corpus de texto plano (`*_respuestas.txt`) listos para cargarse en HDFS.
Para subir automáticamente a HDFS tras la exportación añade `--hdfs-base /data/input --compose-file distributed-batch-ling/deploy/docker-compose.yml`.

## Observabilidad y métricas

- Los logs de Pig se almacenan en `logs/pig_*.log` y se usan para medir duración.
- `scripts/metrics.py` ejecuta `hdfs dfs -count` y `wc -l` dentro del NameNode para obtener tamaños y registros.
- El HistoryServer queda expuesto en `http://localhost:8188` (puerto por defecto del contenedor BDE) para consultar ejecuciones pasadas.

## Entregables

- `docs/batch_analysis/informe.tex`: documentación técnica y guía de demostración.
- `distributed-batch-ling/artifacts/`: resultados obtenidos tras ejecutar el análisis.
- Video demostrativo (no incluido en el repositorio) siguiendo la guía del informe.
