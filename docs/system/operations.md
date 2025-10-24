# Operación y mantenimiento

Este documento resume las tareas operativas más habituales para trabajar con la plataforma.

## Preparación del entorno
1. Clonar el repositorio y situarse en la raíz del proyecto.
2. Revisar las variables de entorno en `docker-compose.yml` y, si es necesario, crear un archivo `.env` para valores específicos.
3. Asegurarse de que Docker y Docker Compose estén instalados y en la versión recomendada por la documentación oficial.

## Despliegue con Docker Compose
```bash
docker compose build
docker compose up -d
```

- El servicio `flink-submit` espera a que el JobManager esté listo antes de enviar `streaming_score_job.py`.
- Utilice `docker compose ps` para verificar que todos los contenedores estén en estado `Up`.
- Monitoree logs con `docker compose logs -f <servicio>`.

## Monitoreo
- **Flink UI** (`http://localhost:8081`): inspeccione el job en ejecución, tareas y métricas como `responses_accepted` y `responses_regenerated`.
- **Kafka**: valide los tópicos existentes con herramientas como `kafka-topics.sh --list` dentro del contenedor de Kafka.
- **MongoDB**: consulte la base usando `mongosh` y verifique la colección `metrics` para estadísticas agregadas.

## Regeneración de respuestas
- El job de Flink envía mensajes a `regeneration_requests` cuando el score cae por debajo de `SCORE_THRESHOLD`.
- El `cache-service` reinyecta estas solicitudes al flujo, evitando ciclos infinitos mediante estados administrados.

## Modo determinista de LLM
- Establezca las variables de entorno definidas en `llm-consumer` para activar el modo offline determinístico.
- Permite reproducir escenarios específicos y evaluar regresiones.

## Apagado y limpieza
```bash
docker compose down
docker compose down -v  # elimina volúmenes y datos persistentes
```

Antes de eliminar volúmenes, asegúrese de respaldar la base de datos si necesita conservar métricas o resultados históricos.

## Desarrollo local
- Los requisitos de Python se encuentran en `requirements.txt` (raíz) y en archivos específicos dentro de cada microservicio para construir las imágenes.
- Puede ejecutar pruebas unitarias o scripts individuales configurando variables de entorno equivalentes a las usadas en Docker.

## Resolución de problemas comunes
| Problema | Causa probable | Acción sugerida |
|----------|----------------|-----------------|
| Tópicos Kafka ausentes | El broker no ha terminado de iniciar | Verifique dependencias en `docker-compose.yml` o reinicie con `docker compose restart kafka`. |
| Flink job no aparece en la UI | `flink-submit` falló al enviar el job | Revise `docker compose logs -f flink-submit` para detectar errores. |
| Respuestas no se almacenan | Umbral de score demasiado alto | Ajuste `SCORE_THRESHOLD` o revise el job de scoring. |
