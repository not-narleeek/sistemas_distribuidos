# Plataforma asíncrona para evaluación de respuestas LLM

La segunda iteración del sistema introduce una arquitectura completamente desacoplada, impulsada por Apache Kafka y Apache Flink, para evaluar respuestas generadas por modelos de lenguaje usando el dataset de Yahoo! Answers.

## Componentes principales

| Componente | Rol | Tecnología |
|------------|-----|------------|
| `traffic-generator` | Publica preguntas en Kafka siguiendo distribuciones configurables. | Python, kafka-python |
| `cache-service` | Revisa MongoDB y la caché local; encola solicitudes al LLM o propaga respuestas válidas. | Python, kafka-python |
| `llm-consumer` | Atiende `llm_requests`, genera respuestas (modo offline por defecto) y maneja errores con *exponential backoff*. | Python |
| `flink-jobmanager` / `flink-taskmanager` | Ejecutan el *job* de Flink que puntúa respuestas, envía regeneraciones y registra métricas. | Apache Flink, PyFlink |
| `storage-service` | Persiste las respuestas validadas y métricas agregadas en MongoDB. | Python, PyMongo |
| `mongo` | Base de datos de preguntas originales y resultados. | MongoDB |
| `kafka` + `zookeeper` | Bus de mensajería distribuido y coordinador. | Confluent Kafka |

Los módulos existentes (generador, caché, almacenamiento) ahora operan como productores/consumidores de Kafka y conviven con nuevos tópicos que orquestan el flujo asíncrono:

- `questions_in`
- `llm_requests`
- `llm_responses`
- `llm_errors`
- `regeneration_requests`
- `validated_responses`

El *job* de Flink calcula la métrica TF-IDF (Tarea 1), decide si aceptar la respuesta o solicitar una regeneración y mantiene estado para evitar bucles infinitos.

## Requisitos

- Docker Engine ≥ 20.10 con soporte para `docker compose` v2.
- 4 GB de RAM libres (Flink y Kafka requieren memoria adicional).
- Puertos disponibles: `2181`, `8081`, `9092`, `27017`.

## Puesta en marcha

```bash
# Construye todas las imágenes personalizadas
docker compose build

# Levanta toda la plataforma
docker compose up -d

# Lanza el job de Flink (se crea automáticamente vía servicio `flink-submit`)
docker compose logs -f flink-submit
```

Los servicios quedan disponibles en la red interna `docker_default`. Puedes inspeccionar su estado con `docker compose ps` y los logs con `docker compose logs -f <servicio>`.

## Configuración rápida

Variables de entorno clave (ver `docker-compose.yml`):

- `CACHE_POLICY`, `CACHE_SIZE`, `CACHE_TTL`: política y parámetros de la caché (default `lru` / `1024` / `3600`).
- `SCORE_THRESHOLD`: umbral mínimo del score (default `0.65`).
- `MAX_RETRIES`: intentos máximos permitidos antes de aceptar una respuesta (default `3`).
- `KAFKA_BOOTSTRAP_SERVERS`: dirección del *broker* para todos los servicios Python.

Puedes personalizar la carga de trabajo del generador ajustando `--total`, `--distribution`, `--lambda`, `--low` y `--high` en la sección correspondiente del compose.

## Flujo de mensajes

![Arquitectura](docs/architecture.puml)

1. `traffic-generator` publica `QuestionMessage` con los metadatos de la pregunta.
2. `cache-service` verifica si existe una respuesta almacenada. Si la hay, produce `ValidatedResponse`; si no, genera un `LLMRequest`.
3. `llm-consumer` responde a cada solicitud y entrega `LLMResponse` (o `ErrorMessage` ante fallos).
4. El *job* de Flink puntúa las respuestas y decide aceptar o solicitar regeneración (`regeneration_requests`).
5. `cache-service` consume regeneraciones y vuelve a invocar al LLM manteniendo el mismo `trace_id`.
6. `storage-service` consume `validated_responses` y actualiza MongoDB junto a métricas agregadas.

## Métricas y observabilidad

- Flink expone contadores `responses_accepted` y `responses_regenerated`, visibles desde la UI web (`http://localhost:8081`).
- `storage-service` mantiene un documento `metrics` con el acumulado de respuestas aceptadas/rechazadas y score medio.
- El generador registra CSV y gráficos en `data_collected/` con la evolución del tráfico emitido.
- Todos los servicios emiten logs en formato JSON (`trace_id`, `message_id`) para facilitar la trazabilidad.

## Experimentos sugeridos

1. **Latencia end-to-end**: medir tiempo entre publicación en `questions_in` y persistencia en MongoDB.
2. **Impacto del umbral**: variar `SCORE_THRESHOLD` y cuantificar tasa de regeneraciones vs. calidad.
3. **Carga paralela**: aumentar particiones en Kafka y `FLINK_PARALLELISM` para estudiar throughput.
4. **Estrategias de caché**: alternar `lru`, `lfu` y `fifo` y comparar hit-rate y latencia.

Los resultados pueden exportarse directamente desde MongoDB o reutilizando los CSV del generador para construir gráficos comparativos.

## Requerimientos de Python

Para ejecutar los servicios sin contenedores utiliza `requirements.txt` en la raíz. Cada microservicio cuenta además con su propio archivo `requirements.txt` optimizado para su imagen Docker.

## Estructura relevante del repositorio

```
common/                       # Modelos de mensaje y utilidades Kafka
cache/cache.py                # Servicio de caché como consumidor/productor Kafka
generador/generador_yahoo.py  # Generador de tráfico hacia Kafka
LLM/kafka_llm_consumer.py     # Servicio LLM asíncrono con backoff
flink_job/streaming_score_job.py # Job PyFlink para scoring y regeneración
storage_service/storage_service.py # Persistencia de respuestas validadas
docs/architecture.puml        # Diagrama PlantUML
```

## Notas adicionales

- El `docker-compose.yml` evita la creación automática de tópicos; el generador inicializa `questions_in`. Los demás servicios crean los necesarios bajo demanda.
- En entornos sin conexión a internet el `llm-consumer` funciona en modo offline y devuelve respuestas determinísticas.
- Se recomienda monitorear el consumo de recursos de Kafka y Flink al aumentar el volumen de mensajes.
- En máquinas Windows (Docker Desktop + WSL2) el arranque del JobManager puede tardar unos segundos adicionales; el servicio `flink-submit` espera ahora a que la API REST (`/jobs/overview`) responda antes de enviar el *job*, evitando errores transitorios como `Job ... not found` en los logs.

Con esta infraestructura modular es posible analizar empíricamente el impacto de un modelo asíncrono en la latencia, throughput y calidad de las respuestas, cumpliendo los objetivos de la Tarea 2.
