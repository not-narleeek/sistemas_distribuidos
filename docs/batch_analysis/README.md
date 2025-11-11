# Informe y artefactos Tarea 3

Este directorio almacena la documentación formal del análisis batch. El archivo principal es `informe.tex`, que puede compilarse con LaTeX (`pdflatex informe.tex`).

## Contenido

- `informe.tex`: descripción de la arquitectura Hadoop/Pig, metodología de limpieza/tokenización, métricas y guía para el video.
- `figures/`: carpeta para gráficos (Top-50, nube de palabras, etc.) generados a partir de los CSV exportados.

## Cómo generar figuras

1. Ejecutar `make fetch` para traer los CSV a `distributed-batch-ling/artifacts/`.
2. Utilizar una herramienta de notebooks (Python, R) o un script dedicado para producir gráficos. Se recomienda guardar las imágenes en `docs/batch_analysis/figures/`.
3. Incluir las figuras en `informe.tex` mediante comandos `\includegraphics`.

## Video demostrativo

La guía de la tarea exige un video de aproximadamente 10 minutos. Sugerimos el siguiente guion:

1. Mostrar la arquitectura general y los contenedores en ejecución (`docker compose ps`).
2. Ejecutar la exportación (`make load-data`) y los trabajos Pig (`make run-batch`).
3. Revisar los logs y métricas (`make metrics`).
4. Presentar los artefactos (`distributed-batch-ling/artifacts/`) y los gráficos generados.
5. Concluir con hallazgos comparativos entre Yahoo! y el LLM.
