# Visión general del sistema

Este repositorio implementa una plataforma distribuida para evaluar respuestas generadas por modelos de lenguaje a partir del dataset de Yahoo! Answers. El sistema se apoya en Kafka y PyFlink para desacoplar la generación de preguntas, el consumo de respuestas y el cálculo de métricas, permitiendo experimentar con políticas de caché, umbrales de calidad y estrategias de reintento.

## Objetivos principales
- Automatizar la evaluación de respuestas generadas por LLMs.
- Medir la calidad y latencia del pipeline de extremo a extremo.
- Permitir pruebas controladas con generadores de tráfico y modos deterministas.

## Servicios desplegados
- **traffic-generator**: produce preguntas siguiendo distribuciones configurables y guarda métricas de entrada en `data_collected/`.
- **cache-service**: resuelve preguntas usando MongoDB y una caché interna; decide si se reutiliza una respuesta o si se envía una nueva solicitud al LLM.
- **llm-consumer**: atiende el tópico `llm_requests`, genera respuestas (modo offline determinístico disponible) y aplica *exponential backoff* ante fallas.
- **Flink (jobmanager/taskmanager/submit)**: ejecuta `streaming_score_job.py`, puntúa respuestas con TF-IDF, controla regeneraciones y mantiene estado para evitar bucles.
- **storage-service**: persiste respuestas validadas y agrega métricas en MongoDB.
- **Infraestructura base**: Kafka, Zookeeper y MongoDB proporcionan mensajería y almacenamiento.

## Flujo de mensajes
El pipeline utiliza seis tópicos Kafka: `questions_in`, `llm_requests`, `llm_responses`, `llm_errors`, `regeneration_requests` y `validated_responses`. El flujo inicia con la publicación de preguntas, continúa con la consulta de caché y generación por el LLM, pasa por el job de Flink para el scoring y finaliza con la persistencia de resultados y métricas.

## Puesta en marcha
1. Construir las imágenes y levantar la plataforma con Docker Compose:
   ```bash
   docker compose build
   docker compose up -d
   ```
2. Verificar el estado de los servicios con `docker compose ps` y consultar logs con `docker compose logs -f <servicio>`.
3. Acceder a la UI de Flink en `http://localhost:8081` para monitorear métricas como `responses_accepted` y `responses_regenerated`.
4. Revisar la colección `metrics` en MongoDB para estadísticas agregadas.

## Configuración
Las variables de entorno y argumentos de cada servicio permiten ajustar:
- Política de caché (`CACHE_POLICY`).
- Umbral mínimo de score (`SCORE_THRESHOLD`).
- Número máximo de reintentos (`MAX_RETRIES`).
- Distribución y volumen de preguntas generadas.

## Requisitos
- Docker y Docker Compose para el despliegue principal.
- Python 3.9+ y dependencias listadas en `requirements.txt` para ejecuciones locales.

## Extensibilidad
La arquitectura modular permite evaluar cambios en la latencia, throughput o calidad ajustando particiones Kafka, paralelismo de Flink o implementando nuevas políticas en los microservicios.
