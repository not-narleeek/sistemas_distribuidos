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

## Guía paso a paso

1. **Validar dependencias del host.**
   - Comprueba que Docker responde ejecutando `docker version`.
   - Verifica que GNU Make funciona con `make --version`.
   - Comprueba que Python 3.10+ está disponible (se usa para los scripts auxiliares) con `python --version`.

2. **Preparar el dataset de respuestas (o tráfico).**
   - El modo por defecto del exportador espera un CSV o Parquet con al menos las columnas `id_pregunta`, `respuesta_texto`, `origen` (`yahoo` o `llm`) y `ts_creacion`.
   - Si tu archivo proviene del monitoreo de colas (campos como `timestamp`, `operation`, `status`, `topic`), ejecuta el script con `--input-schema traffic`. Este modo mapea automáticamente `topic` → `origen` y genera un texto combinando `operation`, `status` y `topic`. Ajusta el comportamiento con `--traffic-text-columns`, `--traffic-origin-map` o `--traffic-origin-default` cuando sea necesario.
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

   Se ejecuta dentro del NameNode y garantiza que existan `/data/input/{yahoo,llm}` y `/data/output/{yahoo,llm}`.

5. **Exportar datos y subirlos a HDFS.**

   ```bash
   make load-data DUMP_PATH=/ruta/a/datos.csv
   ```

   El `Makefile` invoca al exportador para particionar el dataset en `ingestion/output` y después los copia dentro del contenedor `namenode` para publicarlos en HDFS. Si necesitas controlar el proceso manualmente, puedes ejecutar primero el script `exporter.py` y luego `make hdfs-put`.

6. **Ejecutar los jobs de Pig.**

   ```bash
   make run-batch
   ```

   Este target lanza `wordfreq.pig` para Yahoo y LLM, además del comparador. Para ejecuciones individuales existen `make run-yahoo`, `make run-llm` y `make run-compare`.

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
