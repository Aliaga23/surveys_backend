# SurveySaaS Backend

*Back‑end multicanal para la gestión de encuestas, campañas de difusión y analítica de feedback, construido con **FastAPI**, **PostgreSQL** y **Celery**.*

---

## Tabla de contenidos

1. [Características](#características)
2. [Stack tecnológico](#stack-tecnológico)
3. [Estructura del proyecto](#estructura-del-proyecto)
4. [Primeros pasos](#primeros-pasos)
5. [Variables de entorno](#variables-de-entorno)
6. [Tareas en segundo plano](#tareas-en-segundo-plano)
7. [Referencia completa de la API](#referencia-completa-de-la-api)
8. [Despliegue](#despliegue)
---

## Características

* **API RESTful** completa con autenticación JWT y sistema de roles (`admin`, `empresa`, `operator`).
* **Gestión de encuestas de 360°**: plantillas, preguntas, opciones, campañas, entregas, destinatarios y respuestas.
* **Multicanal**: Email, WhatsApp, formularios web PWA, código QR/papel y audio grabado.
* **IA + NLP**: Análisis de sentimiento, resúmenes ejecutivos y chatbot asistido vía OpenAI GPT‑4o.
* **Procesamiento en segundo plano** con Celery + Redis para envíos masivos y jobs costosos.
* **Pagos recurrentes** gestionados con Stripe (planes, checkout y webhooks).
* **PDF generator**: formularios imprimibles por entrega o campaña con QR integrado.
* **Documentación automática** en `/docs` y `/redoc` gracias a FastAPI.

---

## Stack tecnológico

| Capa            | Tecnología                      |
| --------------- | ------------------------------- |
| API / Framework | FastAPI, Pydantic               |
| Base de datos   | PostgreSQL, SQLAlchemy, Alembic |
| Mensajería      | Redis                           |
| Background jobs | Celery                          |
| IA / NLP        | OpenAI GPT‑4o                   |
| Pagos           | Stripe                          |
| E‑mail          | aiosmtplib (SMTP)               |
| Infra ejemplo   | Uvicorn (Railway / Heroku)      |

---

## Estructura del proyecto

```text
surveys_backend/
├── app/
│   ├── core/          # Configuración global, seguridad JWT, DB, celery
│   ├── models/        # ORM SQLAlchemy
│   ├── schemas/       # DTOs Pydantic
│   ├── services/      # Lógica de negocio (emails, IA, pagos, etc.)
│   ├── routers/       # Endpoints agrupados por recurso
│   └── main.py        # Punto de entrada FastAPI
├── migrations/        # Scripts Alembic
├── requirements.txt
├── Procfile           # Para Railway / Heroku
└── README.md
```

---

## Primeros pasos

```bash
# 1. Clonar y crear entorno
$ git clone https://github.com/Aliaga23/surveys_backend.git
$ cd surveys_backend
$ python -m venv .venv
$ source .venv/bin/activate  # Windows: .venv\Scripts\activate
$ pip install -r requirements.txt

# 2. Configurar la base de datos
$ createdb surveys_db  # o via GUI
$ alembic upgrade head

# 3. Copiar variables de entorno
$ cp .env.example .env  # y edita los valores

# 4. Levantar la API
$ uvicorn app.main:app --reload  # http://localhost:8000/docs
```

---

## Variables de entorno

> Las principales se definen en `app/core/config.py`.
> Renombra **.env.example** → **.env** y ajusta.

| Variable                        | Descripción                               |
| ------------------------------- | ----------------------------------------- |
| `DATABASE_URL`                  | Postgres URI (`postgresql+psycopg://...`) |
| `SECRET_KEY`                    | Clave para firmar JWT                     |
| `OPENAI_API_KEY`                | Token GPT‑4o                              |
| `WHAPI_TOKEN` / `WHAPI_API_URL` | Credenciales Whapi                        |
| `STRIPE_*`                      | Claves Stripe (secret, public, webhook)   |
| `SMTP_*`                        | Host, puerto y credenciales SMTP          |
| `REDIS_URL`                     | Broker/Backend Celery                     |
| …                               | (ver `config.py` para la lista completa)  |

---

## Tareas en segundo plano

```bash
# Inicia un worker Celery apuntando al mismo Redis
celery -A app.core.celery.celery worker --loglevel=info --pool=prefork
```

Ejemplos habituales:

* `send_email_task` → e‑mails masivos
* `process_audio_responses` → pipeline STT + OCR

---

## Referencia completa de la API

> **🛈 Tip**: Todos los endpoints devuelven JSON y soportan CORS.
> El prefijo base es `https://<tu‑dominio>/api` si desplegas detrás de un gateway.

### Autenticación (`/auth`)

```http
POST /auth/register/administrador      # Alta de super‑admin
POST /auth/register/suscriptor         # Alta de empresa
POST /auth/register/usuario            # Alta de operador interno
POST /auth/login                       # Obtiene JWT
GET  /auth/me                          # Perfil según rol
POST /auth/request-registration        # Flujo auto‑servicio (e‑mail de verificación)
```

### Catálogos (`/catalogos` · sólo **admin**)

```http
# Roles
POST /catalogos/roles
GET  /catalogos/roles                 
GET  /catalogos/roles/{id}
PUT  /catalogos/roles/{id}
DELETE /catalogos/roles/{id}

# Tipos de pregunta / Canales / Estados / Métodos de pago → mismos verbos CRUD
```

### Suscripciones & Planes (`/subscription`)

```http
# Planes (admin)
POST /subscription/planes
GET  /subscription/planes
GET  /subscription/planes/{plan_id}
PUT  /subscription/planes/{plan_id}
DELETE /subscription/planes/{plan_id}

# Suscripciones (empresa)
POST /subscription/suscripciones
GET  /subscription/suscripciones[?suscriptor_id=]
GET  /subscription/suscripciones/{sus_id}
PUT  /subscription/suscripciones/{sus_id}
DELETE /subscription/suscripciones/{sus_id}

# Stripe helpers
POST /subscription/stripe-suscripcion  # Alta directa vía API
POST /subscription/stripe-checkout     # Sesión Checkout
POST /subscription/stripe-webhook      # Webhooks entrantes
GET  /subscription/stripe-metrics      # Métricas financieras (admin)
```

### Plantillas (`/plantillas`)

```http
POST /plantillas                       # Crear
GET  /plantillas                       # Listar
GET  /plantillas/{plantilla_id}        # Detalle + preguntas
PATCH /plantillas/{plantilla_id}
DELETE /plantillas/{plantilla_id}
```

### Preguntas & Opciones (anidadas)

```http
# Preguntas
POST /plantillas/{plantilla_id}/preguntas
GET  /plantillas/{plantilla_id}/preguntas
GET  /plantillas/{p_id}/preguntas/{pregunta_id}
PATCH /plantillas/{p_id}/preguntas/{pregunta_id}
DELETE /plantillas/{p_id}/preguntas/{pregunta_id}

# Opciones
POST /plantillas/{p_id}/preguntas/{pregunta_id}/opciones
GET  /plantillas/{p_id}/preguntas/{pregunta_id}/opciones
GET  /plantillas/{p_id}/preguntas/{pregunta_id}/opciones/{opcion_id}
PATCH /plantillas/{p_id}/preguntas/{pregunta_id}/opciones/{opcion_id}
DELETE /plantillas/{p_id}/preguntas/{pregunta_id}/opciones/{opcion_id}
```

### Campañas (`/campanas`)

```http
POST /campanas                        # Crear campaña
GET  /campanas                        # Listar
GET  /campanas/{campana_id}
PATCH /campanas/{campana_id}
DELETE /campanas/{campana_id}
GET  /campanas/{campana_id}/full-detail   # Incluye plantilla, entregas y métricas
```

### Destinatarios (`/destinatarios`)

```http
POST /destinatarios                      # Crear contacto
GET  /destinatarios?skip=&limit=
GET  /destinatarios/{dest_id}
PATCH /destinatarios/{dest_id}
DELETE /destinatarios/{dest_id}
POST /destinatarios/upload-excel         # Importación masiva (.xlsx)
```

### Entregas (Privadas)  `/campanas/{campana_id}/entregas`

```http
POST  /                                   # Crear una entrega
POST  /bulk                               # Crear N formularios (papel)
POST  /bulk-audio                         # Crear N entregas de audio (canal 5)
GET   /
GET   /{entrega_id}
PATCH /{entrega_id}
DELETE /{entrega_id}
POST  /{entrega_id}/mark-sent             # → estado ENVIADO
POST  /{entrega_id}/mark-responded        # → estado RESPONDIDO
```

### Entregas (Públicas)  `/public/entregas`

```http
GET  /{entrega_id}/plantilla             # Obtiene plantilla + destinatario
GET  /{entrega_id}/plantilla-mapa        # Modo ligero para OCR
POST /{entrega_id}/respuestas            # Envía respuestas anónimas
GET  /buscar?email=&telefono=            # Autodetecta entrega pendiente
```

### Respuestas

```http
# Administrador
POST   /campanas/{camp_id}/entregas/{e_id}/respuestas
GET    /campanas/{camp_id}/entregas/{e_id}/respuestas
GET    /campanas/{camp_id}/entregas/{e_id}/respuestas/{resp_id}
PATCH  /campanas/{camp_id}/entregas/{e_id}/respuestas/{resp_id}
DELETE /campanas/{camp_id}/entregas/{e_id}/respuestas/{resp_id}

# Público (ya cubierto arriba)
```

### Encuestas tokenizadas (`/encuestas`)

```http
GET  /encuestas/verificar/{token}        # Valida y devuelve contenido
POST /encuestas/responder/{token}        # Envía respuestas (email / PWA)
```

### Analytics & Dashboards

```http
GET /analytics/dashboard                     # KPIs globales por suscriptor
GET /dashboard/campaigns/{camp_id}/analysis  # Resumen GPT‑4 de campaña
```

### Chatbot

```http
POST /chat   # Pregunta libre al asistente IA contextual
```

### WhatsApp Webhooks (`/whatsapp`)

```http
POST /whatsapp/webhook           # Webhook inbound (Whapi)
GET  /whatsapp/webhook           # Verificación (token)
POST /whatsapp/reset/{numero}    # Limpia estado conversacional
GET  /whatsapp/status            # Métricas de conversaciones vivas
POST /whatsapp/send              # Envío manual (test)
```

### PDFs / Formularios (`/entregas`)

```http
GET /entregas/{entrega_id}/formulario.pdf                      # 1 PDF individual
GET /entregas/campanas/{camp_id}/formularios.zip               # ZIP con todos
GET /entregas/campanas/{camp_id}/formularios.pdf               # PDF combinado
```

### Seeder (demo data)  `/seeder`  · **admin only**

```http
POST /seeder/run           # Poblar BD con datos de prueba
POST /seeder/init          # Seed mínimo inicial (roles + admin)
GET  /seeder/status        # Estado actual
DELETE /seeder/clear       # Borra TODO (⚠️ prod‑danger)
DELETE /seeder/clear-test-data   # Borra solo los datos de prueba
```

---

## Despliegue

### Railway / Heroku

```Procfile
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

> Añade los addons de PostgreSQL y Redis, y define todas las variables de entorno.

### Docker (opcional)

```Dockerfile
FROM python:3.12-slim
WORKDIR /code
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Contribuciones

1. Haz *fork* y crea una rama descriptiva.
2. Sigue `black` + `isort` para formatear.
3. Aporta tests donde sea posible.
4. Abre un **Pull Request**.

---

