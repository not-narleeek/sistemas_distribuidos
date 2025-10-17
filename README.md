# Sistema distribuido para evaluación de respuestas LLM

Sistema distribuido modular que simula tráfico de usuarios, consulta un modelo LLM, evalúa la calidad de sus respuestas frente a Yahoo! Answers y persiste métricas reproducibles.

## Requisitos previos

- Docker Engine 20.10 o superior.
- Docker Compose 1.29 o superior.
- Al menos 2 GB de RAM disponibles.
- Puertos libres: `27017`, `5000`, `6000`, `7000`, `7100`.

## Arquitectura del sistema

El ecosistema se compone de siete servicios cooperando en red:

- **mongo**: Base de datos que almacena las preguntas de Yahoo! Answers.
- **init-mongo**: Inicializa MongoDB importando los datos sólo si la colección no existe.
- **llm**: Cliente Gemini que consulta el modelo `gemini-1.5-flash` con _rate limiting_ y reintentos.
- **score**: Servicio encargado de calcular la similitud (coseno TF-IDF) entre la respuesta humana y la respuesta LLM.
- **storage**: Microservicio responsable de persistir las respuestas, contadores de acceso y métricas agregadas.
- **cache**: Servicio de caché con políticas `LRU`, `LFU` o `FIFO`, TTL configurable y registro de latencias/hit-rate.
- **generador**: Generador de tráfico configurable que extrae preguntas desde un CSV (`train/test`) o desde MongoDB.

## Estructura del repositorio

```
├── build.sh                  # Script para construir todas las imágenes
├── run.sh                    # Script para iniciar la plataforma
├── docker-compose.yml        # Orquestación de servicios
├── cache/
│   ├── cache.py
│   ├── Dockerfile
│   └── requirements.txt
├── generador/
│   ├── generador_yahoo.py
│   ├── Dockerfile
│   └── requirements.txt
├── LLM/
│   ├── dummy_LLM.py
│   ├── Dockerfile
│   └── requirements.txt
├── score_service/
│   ├── score_service.py
│   ├── Dockerfile
│   └── requirements.txt
├── storage_service/
│   ├── storage_service.py
│   ├── Dockerfile
│   └── requirements.txt
├── mongo-init/
│   ├── bdd.json
│   ├── Dockerfile
│   └── init.sh
└── data/
    └── yahoo_sample.csv      # Ejemplo de dataset compatible con train/test
```

## Despliegue

### 1. Clonar el repositorio

```bash
git clone <url-del-repo>
cd sistemas_distribuidos
```

### 2. Construir las imágenes

```bash
./build.sh
```

### 3. Iniciar los servicios

```bash
./run.sh
```

Los servicios se inicializan en el siguiente orden: MongoDB → storage/score → LLM → importador → caché → generador. Puedes comprobar el estado con `docker-compose ps`.

> **Nota:** Si dispones de una API key propia puedes exportarla antes de iniciar los contenedores con `export GEMINI_API_KEY="tu_api_key"`. El `docker-compose.yml` incluye un valor por defecto provisto para las pruebas.

### 4. Verificación rápida

- **Inicialización de MongoDB**: `docker-compose logs init-mongo`
- **Conteo de documentos**: `docker exec -it mongo_yahoo mongosh yahoo_db --eval "db.questions.countDocuments()"`
- **Logs de servicios**: `docker-compose logs -f <servicio>`

## Configuración

### Servicio de caché

Parámetros relevantes (ver `docker-compose.yml`):

- `--policy`: Política de reemplazo (`lru`, `lfu`, `fifo`).
- `--size`: Capacidad máxima (entradas).
- `--ttl`: Tiempo de vida en segundos por entrada.
- `--dummy_host/--dummy_port`: Host y puerto del servicio LLM.
- `--score_host/--score_port`: Host y puerto del servicio de scoring.
- `--storage_host/--storage_port`: Host y puerto del servicio de almacenamiento.

Puedes consultar métricas agregadas con:

```bash
docker exec -it cache nc localhost 5000 <<<'STATS'
```

### Servicio de scoring

Expone un servidor TCP (puerto `7000`) que recibe payloads JSON con `question_id`, `best_answer` y `llm_answer`. Devuelve el puntaje normalizado (0–1) y una bandera `accepted` usando un umbral configurable (`--threshold`).

### Servicio de almacenamiento

Guarda documentos con el siguiente esquema base:

```json
{
  "id_pregunta": "...",
  "pregunta": "...",
  "respuesta_dataset": "...",
  "respuesta_llm": "...",
  "score": 0.82,
  "aceptado": true,
  "contador_consultas": 5,
  "ultima_actualizacion": "2024-05-01T00:00:00Z"
}
```

Además mantiene un documento `metrics` con hit/miss acumulado, latencia y puntaje promedio para análisis experimental.

### Generador de tráfico

Parámetros soportados:

- `--dist`: `poisson` o `uniform`.
- `--lmbda`, `--low`, `--high`: Parámetros de llegada.
- `--n`: Cantidad de consultas por ciclo.
- `--dataset_csv`: Ruta opcional a `train.csv`/`test.csv` o al archivo de ejemplo `data/yahoo_sample.csv`.
- `--mongo` / `--db` / `--coll`: Fuente alternativa en MongoDB.
- `--cache_host` / `--cache_port`: Destino para enviar las consultas.
- `--output_dir`: Directorio donde se guardarán los resultados y gráficas (por defecto `data_collected/`).

Cada corrida genera automáticamente un CSV nombrado con las características del experimento (distribución, parámetros de llegada y configuración de caché) dentro de `data_collected/`. Además se crean gráficas (`plots/`) con la evolución de la latencia, los puntajes obtenidos y la distribución HIT/MISS.

Las variables de entorno `CACHE_POLICY`, `CACHE_SIZE`, `CACHE_TTL` y `GENERATOR_OUTPUT_DIR` (definidas en `docker-compose.yml`) permiten reutilizar los mismos valores tanto en la caché como en el generador y controlar la ubicación de los artefactos.

### Servicio LLM (Gemini)

- Requiere definir la variable `GEMINI_API_KEY` (o usar el valor por defecto configurado en `docker-compose.yml`).
- Parámetros clave:
  - `--max_rps`: solicitudes por segundo permitidas.
  - `--max_concurrent`: concurrencia máxima manejada de forma segura.
  - `--gemini_model`: modelo de Gemini a utilizar (por defecto `gemini-1.5-flash`).
  - `--gemini_timeout`, `--gemini_retries`, `--gemini_backoff`: controlan reintentos y _timeouts_ frente a errores transitorios.
- El servicio construye un prompt contextualizado con el título y el contenido de la pregunta y delega la generación a la API oficial de Gemini, retornando la respuesta directamente al servicio de caché.

## Gestión

- **Detener servicios**: `docker-compose down`
- **Detener y eliminar datos**: `docker-compose down -v`
- **Revisar logs**: `docker-compose logs -f`

## Instrumentación y análisis

- El servicio de caché registra métricas de latencia e hit-rate accesibles vía `STATS` y enviadas al servicio de almacenamiento.
- El generador escribe los CSV y gráficos de cada ejecución en `data_collected/` (montado como volumen). Los nombres incluyen distribución, parámetros y política de caché para facilitar la trazabilidad.
- Los resultados normalizados quedan en MongoDB y pueden consultarse para generar informes adicionales.

## Recursos adicionales

- `data/yahoo_sample.csv`: Ejemplo mínimo compatible con `train.csv`/`test.csv`.
- `data_collected/`: Carpeta vacía (con `.gitkeep`) preparada para recibir los CSV y gráficas generadas durante la ejecución.

Con esta arquitectura modular es posible variar políticas de caché, tamaños, distribuciones de tráfico y umbrales de aceptación para realizar experimentos reproducibles sobre la calidad de respuesta del LLM.
