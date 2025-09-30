# Sistema de Caché con MongoDB y LLM

Sistema distribuido de caché inteligente para consultas a un servicio LLM, con generación de peticiones basada en el dataset Yahoo Answers.

## Requisitos Previos

- Docker Engine 20.10 o superior
- Docker Compose 1.29 o superior
- Al menos 2GB de RAM disponible
- Puertos disponibles: 27017, 5000, 6000

## Arquitectura del Sistema

El sistema está compuesto por 5 servicios:

- **mongo**: Base de datos MongoDB para almacenar el dataset de preguntas
- **init-mongo**: Servicio de inicialización que carga los datos en MongoDB
- **cache**: Sistema de caché con política LFU (Least Frequently Used)
- **llm**: Servicio simulado de LLM para responder consultas
- **generador**: Generador de peticiones con distribución Poisson

## Estructura del Proyecto

```
proyecto/
├── docker-compose.yml
├── README.md
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
└── mongo/
    ├── bdd.json
    ├── Dockerfile
    └── init.sh
```

## Despliegue del Sistema

### Paso 1: Clonar el Repositorio

```bash
git clone <url-del-repositorio>
cd proyecto
```

### Paso 2: Construir las Imágenes

Ejecutar el siguiente comando para construir todas las imágenes personalizadas:

```bash
docker-compose build
```

Este proceso puede tomar varios minutos dependiendo de la velocidad de conexión a internet y los recursos del sistema.

### Paso 3: Iniciar el Sistema

Para iniciar todos los servicios en segundo plano:

```bash
docker-compose up -d
```

El sistema iniciará los servicios en el siguiente orden:
1. MongoDB
2. Servicio LLM
3. Inicialización de MongoDB (carga de datos)
4. Sistema de caché
5. Generador de peticiones

### Paso 4: Verificar el Estado de los Servicios

```bash
docker-compose ps
```

Salida esperada:

```
NAME                COMMAND                  SERVICE      STATUS
cache               "python cache.py --p…"   cache        running
dummy_LLM           "python dummy_LLM.py"    llm          running
generador_yahoo     "python generador_ya…"   generador    running
mongo_yahoo         "docker-entrypoint.s…"   mongo        running
```

El servicio `init-mongo` debe aparecer con estado "exited" y código de salida 0, indicando que la inicialización fue exitosa.

## Verificación del Despliegue

### Verificar Inicialización de MongoDB

Comprobar que los datos se cargaron correctamente:

```bash
docker-compose logs init-mongo
```

Verificar el número de documentos en la base de datos:

```bash
docker exec -it mongo_yahoo mongosh yahoo_db --eval "db.questions.countDocuments()"
```

### Verificar Sistema de Caché

Monitorear el funcionamiento del sistema de caché:

```bash
docker-compose logs -f cache
```

### Verificar Generador de Peticiones

Monitorear la generación de peticiones:

```bash
docker-compose logs -f generador
```

### Verificar Servicio LLM

Comprobar que el servicio LLM está respondiendo:

```bash
docker-compose logs -f llm
```

## Configuración del Sistema

### Parámetros del Sistema de Caché

El servicio de caché se configura mediante los siguientes parámetros en `docker-compose.yml`:

- `--policy lfu`: Política de reemplazo (Least Frequently Used)
- `--size 500`: Tamaño máximo de la caché en número de entradas
- `--mongo mongodb://mongo:27017/`: URL de conexión a MongoDB
- `--db yahoo_db`: Nombre de la base de datos
- `--coll questions`: Nombre de la colección de preguntas
- `--dummy_host dummy_LLM`: Hostname del servicio LLM
- `--dummy_port 6000`: Puerto del servicio LLM

### Parámetros del Generador

El generador de peticiones acepta los siguientes parámetros:

- `--dist poisson`: Distribución estadística para generación de peticiones
- `--n 8000`: Número total de peticiones a generar
- `--mongo mongodb://mongo:27017/`: URL de conexión a MongoDB
- `--db yahoo_db`: Nombre de la base de datos
- `--coll questions`: Nombre de la colección
- `--cache_host cache`: Hostname del servicio de caché
- `--cache_port 5000`: Puerto del servicio de caché

### Modificar Configuración

Para modificar la configuración del sistema, editar el archivo `docker-compose.yml` y ajustar los parámetros en la sección `command` del servicio correspondiente. Luego reiniciar el servicio:

```bash
docker-compose up -d <nombre-servicio>
```

## Gestión del Sistema

### Detener el Sistema

Para detener todos los servicios:

```bash
docker-compose down
```

### Detener y Eliminar Datos

Para detener el sistema y eliminar los volúmenes de datos:

```bash
docker-compose down -v
```

**Advertencia**: Este comando eliminará todos los datos almacenados en MongoDB.

### Visualizar Logs

Ver logs de todos los servicios en tiempo real:

```bash
docker-compose logs -f
```

Ver logs de un servicio específico:

```bash
docker-compose logs -f <nombre-servicio>
```

Ejemplos:
```bash
docker-compose logs -f cache
docker-compose logs -f mongo
docker-compose logs -f generador
```

Ver últimas N líneas de logs:

```bash
docker-compose logs --tail=100 <nombre-servicio>
```

### Reiniciar Servicios

Reiniciar un servicio específico:

```bash
docker-compose restart <nombre-servicio>
```

Reiniciar todos los servicios:

```bash
docker-compose restart
```

### Reconstruir Servicios

Si se realizan cambios en el código, reconstruir e iniciar el servicio:

```bash
docker-compose build <nombre-servicio>
docker-compose up -d <nombre-servicio>
```

Ejemplo para el servicio de caché:

```bash
docker-compose build cache
docker-compose up -d cache
```

### Acceder a Contenedores

Acceder a la shell de MongoDB:

```bash
docker exec -it mongo_yahoo mongosh
```

Acceder a la shell de un contenedor:

```bash
docker exec -it <nombre-contenedor> /bin/bash
```

O si el contenedor usa Alpine Linux:

```bash
docker exec -it <nombre-contenedor> /bin/sh
```

## Monitorización y Diagnóstico

### Monitorear Recursos del Sistema

Ver uso de CPU, memoria y red de todos los contenedores:

```bash
docker stats
```

Ver estadísticas de un contenedor específico:

```bash
docker stats <nombre-contenedor>
```

### Inspeccionar Red

Ver configuración de la red:

```bash
docker network inspect proyecto_default
```

### Inspeccionar Volúmenes

Listar volúmenes:

```bash
docker volume ls
```

Inspeccionar el volumen de MongoDB:

```bash
docker volume inspect proyecto_mongo_data
```

### Verificar Conectividad entre Servicios

Probar conectividad desde el servicio de caché a MongoDB:

```bash
docker exec -it cache ping mongo
```

Probar conectividad desde el generador al servicio de caché:

```bash
docker exec -it generador_yahoo ping cache
```

## Solución de Problemas

### Problema: El servicio init-mongo falla

**Síntomas**: El servicio `init-mongo` no completa la inicialización correctamente.

**Solución**:

1. Verificar que MongoDB está completamente iniciado:
   ```bash
   docker-compose logs mongo
   ```

2. Verificar logs del servicio de inicialización:
   ```bash
   docker-compose logs init-mongo
   ```

3. Reintentar la inicialización:
   ```bash
   docker-compose up init-mongo
   ```

4. Si persiste el problema, verificar permisos del archivo `bdd.json`:
   ```bash
   ls -l mongo/bdd.json
   ```

### Problema: Puertos ya en uso

**Síntomas**: Error indicando que un puerto está ocupado al iniciar los servicios.

**Solución**:

Verificar qué proceso está usando el puerto:

```bash
# En Linux/Mac
sudo lsof -i :<puerto>
# En Windows
netstat -ano | findstr :<puerto>
```

Modificar el mapeo de puertos en `docker-compose.yml`:

```yaml
ports:
  - "<nuevo-puerto-host>:<puerto-contenedor>"
```

Ejemplo para cambiar el puerto de MongoDB:

```yaml
ports:
  - "27018:27017"  # Usar puerto 27018 en el host
```

### Problema: Servicios no se comunican entre sí

**Síntomas**: Los servicios no pueden conectarse entre ellos.

**Solución**:

1. Verificar que todos los servicios están en la misma red:
   ```bash
   docker network inspect proyecto_default
   ```

2. Verificar resolución DNS entre contenedores:
   ```bash
   docker exec -it cache ping mongo
   docker exec -it cache ping dummy_LLM
   ```

3. Verificar que los servicios están escuchando en los puertos correctos:
   ```bash
   docker exec -it mongo_yahoo netstat -tuln
   ```

4. Revisar configuración de firewall del host si los contenedores no pueden comunicarse.

### Problema: MongoDB no tiene datos después de la inicialización

**Síntomas**: La base de datos está vacía o no contiene los datos esperados.

**Solución**:

1. Verificar que el archivo `bdd.json` existe y contiene datos válidos:
   ```bash
   cat mongo/bdd.json | head -20
   ```

2. Verificar logs del servicio de inicialización:
   ```bash
   docker-compose logs init-mongo
   ```

3. Eliminar el volumen y reiniciar:
   ```bash
   docker-compose down -v
   docker-compose up -d
   ```

### Problema: Contenedor se reinicia constantemente

**Síntomas**: Un contenedor entra en un loop de reinicios.

**Solución**:

1. Ver logs del contenedor problemático:
   ```bash
   docker-compose logs --tail=50 <nombre-servicio>
   ```

2. Verificar dependencias de Python:
   ```bash
   docker-compose build --no-cache <nombre-servicio>
   ```

3. Ejecutar el contenedor en modo interactivo para debugging:
   ```bash
   docker-compose run --rm <nombre-servicio> /bin/bash
   ```

### Problema: Alto uso de memoria

**Síntomas**: El sistema consume demasiada memoria.

**Solución**:

1. Verificar uso de recursos:
   ```bash
   docker stats
   ```

2. Reducir el tamaño de la caché en `docker-compose.yml`:
   ```yaml
   command: ["--policy", "lfu", "--size", "200", ...]
   ```

3. Reducir el número de peticiones del generador:
   ```yaml
   command: ["--dist", "poisson", "--n", "5000", ...]
   ```

4. Limitar memoria de MongoDB en `docker-compose.yml`:
   ```yaml
   deploy:
     resources:
       limits:
         memory: 512M
   ```

### Reinicio Completo del Sistema

Si los problemas persisten, realizar un reinicio completo:

```bash
docker-compose down -v
docker system prune -a -f
docker-compose build --no-cache
docker-compose up -d
```

**Advertencia**: Este proceso eliminará todas las imágenes, contenedores y volúmenes. Solo usar como último recurso.

## Puertos Utilizados

| Servicio | Puerto Host | Puerto Contenedor | Descripción |
|----------|-------------|-------------------|-------------|
| MongoDB  | 27017       | 27017            | Base de datos |
| Cache    | 5000        | 5000             | API de caché |
| LLM      | 6000        | 6000             | Servicio LLM |

## Persistencia de Datos

Los datos de MongoDB se almacenan en un volumen Docker persistente llamado `mongo_data`. Este volumen mantiene los datos incluso cuando los contenedores se detienen o eliminan, a menos que se use el flag `-v` con `docker-compose down`.

Para hacer un backup del volumen:

```bash
docker run --rm -v proyecto_mongo_data:/data -v $(pwd):/backup ubuntu tar czf /backup/mongo_backup.tar.gz /data
```

Para restaurar un backup:

```bash
docker run --rm -v proyecto_mongo_data:/data -v $(pwd):/backup ubuntu tar xzf /backup/mongo_backup.tar.gz -C /
```

## Notas Adicionales

- El servicio `init-mongo` tiene configurado `restart: "no"` porque debe ejecutarse una sola vez para cargar los datos iniciales.
- Los servicios `mongo`, `cache`, `llm` y `generador` tienen configurado `restart: on-failure` para reiniciarse automáticamente en caso de fallos.
- Todos los servicios se comunican a través de una red bridge predeterminada creada por Docker Compose.
- Los nombres de host dentro de la red Docker corresponden a los nombres de los servicios definidos en `docker-compose.yml`.
- El generador finaliza su ejecución después de generar las N peticiones especificadas.

## Mantenimiento

### Actualización del Sistema

Para actualizar el código y reconstruir los servicios:

```bash
git pull
docker-compose down
docker-compose build
docker-compose up -d
```

### Limpieza de Recursos

Eliminar imágenes no utilizadas:

```bash
docker image prune -a
```

Eliminar contenedores detenidos:

```bash
docker container prune
```

Eliminar redes no utilizadas:

```bash
docker network prune
```

Limpieza completa del sistema Docker:

```bash
docker system prune -a --volumes
```

## Soporte y Contribuciones

Para reportar problemas, solicitar funcionalidades o contribuir al proyecto, crear un issue o pull request en el repositorio del proyecto.
