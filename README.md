# Huellas de Esperanza

Plataforma web para consultar animales disponibles, registrar solicitudes y gestionar el proceso de adopción. Proyecto académico de Arquitectura Orientada a Servicios (SOA).

## Arquitectura

```mermaid
flowchart LR
    Browser[Frontend web] -->|HTTP/JSON| Pets[API Mascotas<br/>FastAPI :8001]
    Browser -->|HTTP/JSON| Adoptions[API Adopciones<br/>FastAPI :8002]
    Adoptions -->|HTTP/JSON: disponibilidad, reservar, confirmar| Pets
    Pets -->|tabla pets| Supabase[(PostgreSQL / Supabase)]
    Adoptions -->|tabla adoptions| Supabase
```

Son dos aplicaciones independientes con responsabilidades y tablas propias. Comparten el proyecto PostgreSQL de Supabase para simplificar el despliegue académico, pero la API de Adopciones **no** lee ni modifica la tabla `pets`: consulta y coordina esos cambios exclusivamente mediante la API de Mascotas. Cada API publica su propia documentación OpenAPI.

### Flujo y consistencia

1. El frontend consulta las mascotas disponibles en Mascotas.
2. Al enviar una solicitud, Adopciones consulta por HTTP el estado actual de la mascota y crea una solicitud `pending`.
3. Al aprobarla, Adopciones pide una reserva a Mascotas. Una actualización condicional de la base de datos permite reservar solo si el estado sigue `available`; las aprobaciones simultáneas para la misma mascota no pueden ganar ambas.
4. Adopciones cambia la solicitud a `approved` (con índice único parcial por mascota) y pide confirmar la adopción a Mascotas, que cambia `reserved` a `adopted`.
5. Si falla la escritura de aprobación, Adopciones libera la reserva. Si falla la confirmación, revierte la solicitud y compensa liberando la reserva; el error se devuelve explícitamente.

La coordinación entre dos servicios no es una transacción distribuida. La reserva más las compensaciones implementan una saga sencilla para el alcance del examen; en producción se añadirían reintentos, idempotencia durable/outbox, autenticación y observabilidad para recuperar fallos prolongados.

### Modelo de datos

**`pets` (propiedad de API Mascotas)**

| Campo | Descripción |
|---|---|
| `id` | Identificador de la mascota |
| `name`, `species`, `breed`, `age`, `description`, `photo_url` | Información pública del animal |
| `status` | `available`, `reserved` o `adopted` |
| `reservation_id` | ID de la solicitud que tiene la reserva; único mientras no sea nulo |

**`adoptions` (propiedad de API Adopciones)**

| Campo | Descripción |
|---|---|
| `id` | Identificador de la solicitud |
| `pet_id` | Identificador remoto de mascota (no FK: lo administra otro servicio) |
| `applicant_name`, `email`, `phone`, `motivation` | Datos del solicitante |
| `status` | `pending`, `approved` o `rejected` |
| `created_at` | Fecha de creación |

Un índice único parcial permite como máximo una fila `approved` por `pet_id`.

## Ejecutar localmente

Requisitos: Docker Desktop con Docker Compose. Desde la raíz:

```powershell
docker compose up --build
```

- Web: <http://localhost:8080>
- Mascotas: <http://localhost:8001/docs>
- Adopciones: <http://localhost:8002/docs>
- Health checks: `http://localhost:8001/health` y `http://localhost:8002/health`

La base PostgreSQL local conserva los datos en el volumen `postgres_data`. Para detener los servicios: `docker compose down`. No uses `docker compose down -v` si quieres conservarlos.

También se pueden ejecutar las APIs directamente con Python 3.12+: instala `requirements.txt`, configura `DATABASE_URL` (por defecto cada servicio usa SQLite `huellas.db`) y arranca en terminales separadas:

```powershell
python -m pip install -r requirements.txt
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/huellas"
$env:FRONTEND_ORIGINS = "http://localhost:8080"
uvicorn services.pets.main:app --port 8001 --reload
```

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/huellas"
$env:PETS_API_URL = "http://localhost:8001"
$env:FRONTEND_ORIGINS = "http://localhost:8080"
uvicorn services.adoptions.main:app --port 8002 --reload
```

Sirve `frontend/` con un servidor estático (por ejemplo, `python -m http.server 8080 --directory frontend`) en otra terminal. Para cambiar las URL del navegador, edita `frontend/config.js`.

## Conectar una base Supabase para pruebas locales

1. En [Supabase](https://supabase.com/), crea un proyecto y guarda la contraseña de base de datos. Espera a que termine el aprovisionamiento.
2. En el panel del proyecto abre **Connect** y elige una URI PostgreSQL compatible con tu red. Si la conexión directa no funciona por IPv4, utiliza **Session pooler**. Copia la URI completa que muestra el panel; no publiques la contraseña.
3. En PowerShell, desde la raíz del proyecto, crea tu archivo local de variables:

   ```powershell
   Copy-Item .env.example .env
   notepad .env
   ```

4. En `.env`, reemplaza el valor de `DATABASE_URL` con la URI copiada. Si el panel muestra `postgresql://...`, también se admite; la aplicación la convierte al driver Psycopg. Asegúrate de que incluya `sslmode=require` si Supabase lo indica. Si la contraseña contiene caracteres reservados de URL (`@`, `:`, `/`, `#`, `%`, `?`), codifícala como URL antes de insertarla. No pegues la URI con contraseña en el chat ni la guardes en Git.
5. Guarda `.env`, detén el Compose anterior con `Ctrl+C` y, desde otra terminal en la raíz, ejecuta:

   ```powershell
   docker compose down
   docker compose up --build
   ```

   Compose carga `.env` automáticamente. Los dos servicios reciben el mismo `DATABASE_URL`, pero cada uno crea y administra su propia tabla (`pets` o `adoptions`). El contenedor PostgreSQL local puede seguir iniciándose; al usar una URI Supabase, las APIs se conectan a Supabase, no a esa base local.
6. Espera a ver `Application startup complete` en los logs de ambas APIs. Abre <http://localhost:8001/docs> y <http://localhost:8002/docs>. Al iniciar, las APIs crean las tablas automáticamente.
7. En Supabase, abre **Table Editor** y verifica que existan `pets` y `adoptions`. Para probar la integración: registra una mascota en Swagger de Mascotas; crea dos solicitudes para ella en Swagger de Adopciones; aprueba la primera y comprueba que la segunda devuelve `409`. La mascota debe terminar con estado `adopted` y la solicitud con estado `approved`.

Si no conecta, revisa que el proyecto Supabase esté activo, que la URI y la contraseña sean correctas y que los logs de las APIs no indiquen error de autenticación o red. No compartas aquí la URI con credenciales; puedes compartir el mensaje de error ocultando usuario, host sensible y contraseña.

Para volver a PostgreSQL local, restaura en `.env` el valor de `DATABASE_URL` que aparece en `.env.example` y reinicia Compose.

### Despliegue en la nube

1. Despliega cada servicio como un servicio web independiente (Render, Railway u otra plataforma Docker), con su Dockerfile, contexto de construcción en la raíz y puerto interno `8000`.
2. Configura `DATABASE_URL` en ambos servicios con la URI Supabase. Configura `PETS_API_URL` en Adopciones con la URL pública de Mascotas.
3. Configura `FRONTEND_ORIGINS` en ambas APIs con el origen exacto del frontend desplegado.
4. Publica el contenido de `frontend/` en un hosting estático y actualiza `frontend/config.js` con las dos URL públicas de API.
5. Prueba `/health`, `/docs` y el flujo de solicitud/aprobación en el sitio desplegado. Configura TLS y no reutilices las credenciales locales de Compose.

Las tablas se crean al iniciar cada API para facilitar la demostración. En un entorno real conviene administrar cambios de esquema con migraciones (Alembic) en lugar de `create_all`.

Este prototipo no incluye autenticación ni roles: el formulario de registro y las acciones de aprobar/rechazar son demostrativos y no deben exponerse como panel administrativo en producción.

## Endpoints principales

| Servicio | Método y ruta | Función |
|---|---|---|
| Mascotas | `POST /pets` | Registrar una mascota |
| Mascotas | `GET /pets?available_only=true` | Consultar disponibilidad |
| Mascotas | `GET /pets/{id}` | Consultar una mascota |
| Mascotas | `POST /pets/{id}/reservations` | Reservar para una solicitud (integración) |
| Mascotas | `POST /pets/{id}/complete-adoption` | Confirmar adopción (integración) |
| Mascotas | `DELETE /pets/{id}/reservations` | Liberar reserva por compensación |
| Adopciones | `POST /adoptions` | Crear solicitud pendiente |
| Adopciones | `GET /adoptions` | Consultar solicitudes |
| Adopciones | `GET /adoptions/{id}` | Consultar una solicitud |
| Adopciones | `POST /adoptions/{id}/approve` | Aprobar y coordinar con Mascotas |
| Adopciones | `POST /adoptions/{id}/reject` | Rechazar solicitud pendiente |

Las respuestas de conflicto usan `409` (por ejemplo, mascota ya reservada o solicitud ya gestionada); indisponibilidad de la API remota usa `503`.

## Pruebas

Con dependencias instaladas, ejecuta desde la raíz:

```powershell
pytest -q
```

La prueba de flujo pasa por ambos contratos HTTP de forma integrada y verifica que una segunda solicitud no pueda aprobarse para una mascota ya adoptada.

## Guion sugerido para socialización (7 minutos)

1. **Problema y demo (1 min):** mostrar disponibilidad y crear una solicitud desde el frontend.
2. **SOA (1.5 min):** explicar que cada API tiene responsabilidad, contrato y documentación propios.
3. **Integración (1.5 min):** enseñar en Swagger la aprobación: Adopciones llama a Mascotas por REST/JSON para reservar y confirmar.
4. **Datos y consistencia (1 min):** explicar tablas, estados, reserva condicional e índice único; mostrar el rechazo de una segunda aprobación.
5. **Decisiones y despliegue (1 min):** FastAPI, PostgreSQL/Supabase, frontend estático y variables de entorno.
6. **Cierre (1 min):** mencionar límites del prototipo y mejoras de producción (autenticación, migraciones, saga durable).
