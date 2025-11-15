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
scripts/discover_traffic_runs.py # Manifest con runs FIFO/LFU/LRU
scripts/normalize_traffic_csv.py # Normalización y esquema canónico para Pig
scripts/hdfs_put_traffic.py # Publica datasets normalizados en HDFS
scripts/run_traffic_analysis.py # Orquesta Pig traffic_analysis.pig por combinación
scripts/fetch_traffic_results.py # Copia resultados de HDFS al host
scripts/compare_policies_distributions.py # Resumen comparativo de políticas/distribuciones
pig/traffic_analysis.pig   # Pig Latin para métricas por política/distribución
```

## Prerrequisitos

- Docker Engine ≥ 20.10 con soporte `docker compose` v2.
- GNU Make, Python 3.10+.
- Archivo CSV/Parquet o acceso a MongoDB con columnas: `id_pregunta`, `respuesta_texto`, `origen`, `ts_creacion`.
- Conexión a Internet la primera vez (descarga Pig 0.17.0).

## Guía paso a paso

1. **Validar dependencias del host.**
   - Comprueba que Docker responde ejecutando `docker version`.
   - Verifica que GNU Make funciona con `make --version`.
   - Comprueba que Python 3.10+ está disponible (se usa para los scripts auxiliares) con `python --version`.

2. **Preparar el dataset de respuestas (o tráfico).**
   - En modo `auto` (valor por defecto), el exportador inspecciona las cabeceras del CSV y decide si usar el esquema de **respuestas** (`id_pregunta`, `respuesta_texto`, `origen`, `ts_creacion`) o el de **telemetría de colas** (`timestamp`, `operation`, `status`, `topic`, etc.).
   - Si prefieres forzar un modo concreto, añade `--input-schema responses` o `--input-schema traffic`. En el modo *traffic* puedes ajustar el comportamiento con `--traffic-text-columns`, `--traffic-origin-map` o `--traffic-origin-default`.
   - En cualquier caso puedes validar el esquema rápidamente con:

     ```bash
     python distributed-batch-ling/ingestion/exporter.py \
       --input /ruta/a/datos.csv \
       --output-dir distributed-batch-ling/ingestion/output \
       --dry-run --verbose
     ```

     Esto revisa el esquema sin escribir archivos. Repite el paso tras ajustar los nombres/valores hasta que el proceso finalice sin errores.

3. **Construir y arrancar el clúster Hadoop + Pig.**

   ```bash
   make up
   ```

   El comando descarga/compila las imágenes necesarias y levanta los servicios definidos en `deploy/docker-compose.yml`. Puedes observar el estado con `make ps` y consultar logs con `make logs`.

4. **Crear las rutas base en HDFS.**

   ```bash
   make hdfs-init
   ```

   Se ejecuta dentro del NameNode, espera a que HDFS salga de *safe mode*, garantiza que existan `/data/input/{yahoo,llm}` y
   `/data/output/{yahoo,llm}` y publica `stopwords_es.txt` en `/data/resources/stopwords_es.txt` dentro de HDFS para que los
   nodos de MapReduce puedan leerlo.

5. **Exportar datos y subirlos a HDFS.**

   ```bash
   make load-data DUMP_PATH=/ruta/a/datos.csv
   ```

   El `Makefile` invoca al exportador (que detecta automáticamente el esquema cuando no se especifica) para particionar el dataset en `ingestion/output` y después los copia dentro del contenedor `namenode` para publicarlos en HDFS. Si necesitas forzar manualmente el modo tráfico o personalizarlo, añade `SCHEMA=traffic` y (opcionalmente) los parámetros `TRAFFIC_TEXT_COLUMNS`, `TRAFFIC_ORIGIN_MAP`, etc., por ejemplo:

   ```bash
   make load-data DUMP_PATH=./data_collected/traffic/archivo.csv SCHEMA=traffic TRAFFIC_TEXT_COLUMNS=operation,status,topic
   ```

   Si necesitas controlar el proceso manualmente, puedes ejecutar primero el script `exporter.py` y luego `make hdfs-put`.

6. **Ejecutar los jobs de Pig.**

   ```bash
   make run-batch
   ```

   Este target lanza `wordfreq.pig` para Yahoo y LLM, además del comparador. Para ejecuciones individuales existen `make run-yahoo`, `make run-llm` y `make run-compare`.

   Antes de cada ejecución se eliminan las rutas de salida previas en HDFS para evitar el error de "Output directory ... already exists" que impide volver a correr los *jobs* sin limpiar manualmente.

7. **Descargar los resultados al host.**

   ```bash
   make fetch
   ```

   Los artefactos quedarán en `artifacts/output/` replicando la estructura de HDFS.

8. **Generar tablas, Top-N y visualizaciones opcionales.**

   ```bash
   make compare CHART=1
   ```

   El script `scripts/compare_topn.py` toma los TSV descargados y produce CSV/PNG para incluir en el informe. Omite `CHART=1` si sólo necesitas tablas.

9. **Calcular métricas agregadas.**

    ```bash
    make metrics
    ```

   Esto resume el tamaño de los corpus, el número de tokens y la duración de los jobs leyendo los logs almacenados.

10. **Apagar el entorno cuando termines.**

    ```bash
    make down
    ```

    Usa `make clean-logs` y `make clean-artifacts` para limpiar resultados previos antes de una nueva corrida.

## Flujo de análisis de tráfico (políticas FIFO/LFU/LRU)

El dataset `data_collected/traffic` se recorre automáticamente para producir un manifest de corridas, normalizarlas y ejecutar Pig por cada combinación `(policy, distribution)`. Los archivos resultantes siguen la convención `stats_global_<policy>_<distribution>.tsv` para facilitar el informe.

1. **Descubrir corridas disponibles.**

   ```bash
   make discover-traffic [BASE_DIR=data_collected/traffic]
   ```

   - Genera `data_collected/traffic_manifest.json` con metadatos (`policy`, `distribution`, `n`, `lambda`, etc.).
   - Usa `FORMAT=csv` si quieres inspeccionar el manifest en una hoja de cálculo.

2. **Normalizar CSV crudos.**

   ```bash
   make normalize-traffic [OVERWRITE=1]
   ```

   - Combina todos los runs por `policy`+`distribution` en `data_normalized/traffic/<policy>/<distribution>/traffic_<policy>_<distribution>.csv`.
   - El esquema canónico es:

     | Campo | Descripción |
     | --- | --- |
     | `timestamp_iso` | Marca de tiempo original en ISO 8601. |
     | `operation` | Operación registrada (PUBLISH, HIT, etc.). |
     | `message_id` / `question_id` | Identificadores asociados a cada solicitud. |
     | `status` | Estado derivado de la cola o caché. |
     | `latency_seconds` | Latencia normalizada a segundos (admite separador `,` o `.`). |
     | `topic` | Cola o bucket que recibió la operación. |
     | `policy`, `distribution` | Etiquetas persistidas por fila para no perder contexto. |
     | `is_hit`, `was_evicted` | Señales binarias inferidas del `status` para calcular *hit ratio* y evicciones. |

3. **Publicar datasets en HDFS.**

   ```bash
   make hdfs-put-traffic
   ```

   - Copia cada `traffic_<policy>_<distribution>.csv` al NameNode y lo sube a rutas como:
     - `/data/in/traffic/fifo/poisson/traffic_fifo_poisson.csv`
     - `/data/in/traffic/lru/uniform/traffic_lru_uniform.csv`

4. **Ejecutar Pig para todas las combinaciones.**

   ```bash
   make traffic-analysis
   ```

   - `scripts/run_traffic_analysis.py` recorre el manifest, limpia `/data/out/traffic/<policy>/<distribution>` y lanza
     `pig/traffic_analysis.pig` con los parámetros adecuados.
   - Cada corrida produce tres directorios en HDFS: `stats_global_*`, `stats_by_topic_*` y `stats_by_status_*`.

5. **Traer resultados locales.**

   ```bash
   make fetch-traffic
   ```

   - Copia a `distributed-batch-ling/artifacts/traffic/` los TSV nombrados como
     `stats_global_<policy>_<distribution>.tsv`, etc.

6. **Generar un resumen comparativo.**

   ```bash
   make compare-traffic
   ```

   - El script `scripts/compare_policies_distributions.py` agrega los TSV globales y genera
     `summary_global_policies_distributions.tsv` listo para el informe.

7. **Pipeline completo en un solo comando.**

   ```bash
   make traffic-pipeline
   ```

   Ejecuta todos los pasos anteriores (descubrimiento → normalización → carga → Pig → fetch → resumen) y deja los artefactos en
   `distributed-batch-ling/artifacts/traffic/`.

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
