# statline-backend · Backlog

This repo's slice of the project backlog. The full backlog (61 issues, 277 points) and the board live in [statline-infra docs/BACKLOG.md](https://github.com/statline-iteso/statline-infra/blob/develop/docs/BACKLOG.md).

**Progress:** 31 of 31 issues done · 147 of 147 points.

**How to read it**

- ✅ done (first half: Juan Pablo González; second half: Ian Rodríguez) · ⏳ pending.
- An unticked criterion on a ✅ issue was met in a different way; its note says how and links the decision.
- One issue = one PR (`feature/<issue>-<desc>` → `develop`, squash merge, `Closes #N`).
- Board columns: Backlog → Listo para trabajar → En progreso → En revisión → Terminado.

## E1 · Cimientos del repositorio

### ✅ [SL-02](https://github.com/statline-iteso/statline-backend/issues/1) · Devcontainers y versiones fijadas de herramientas

**Sprint:** S0 · **Points:** 3 · **Priority:** Media

**Acceptance criteria**

- [x] `.devcontainer/devcontainer.json` en backend y frontend (Node 20, Python 3.12, uv, pnpm)
- [x] Versiones fijadas: `.nvmrc`, `.python-version`, `packageManager`, `mise.toml` en infra
- [x] `docker-compose.yml` con PostgreSQL 16 y Redis 7 para desarrollo local

### ✅ [SL-03](https://github.com/statline-iteso/statline-backend/issues/2) · Definir esquemas JSON Schema para métricas de NBA, NFL y Liga MX

**Sprint:** S0 · **Points:** 3 · **Priority:** Alta

**Acceptance criteria**

- [x] `schemas/basquetbol.schema.json`, `americano.schema.json` y `futbol.schema.json` (draft 2020-12)
- [x] `additionalProperties: false` y mínimos en cada métrica
- [x] Pruebas con casos válidos e inválidos por deporte

## E3 · Servicio de ingesta

### ✅ [SL-13](https://github.com/statline-iteso/statline-backend/issues/3) · Esqueleto del servicio de ingesta (Python 3.12, uv, configuración y probes)

**Sprint:** S2 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] Paquete `ingesta` con `pyproject.toml`, uv.lock, ruff y mypy strict
- [x] Configuración por variables de entorno (pydantic-settings)
- [x] `ingesta serve` expone /healthz, /readyz y /metrics

### ✅ [SL-14](https://github.com/statline-iteso/statline-backend/issues/4) · Persistencia en PostgreSQL y auditoría en EjecucionIngesta

**Sprint:** S2 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] Upserts idempotentes de equipo, jugador, partido y estadística (mismas llaves únicas que Prisma)
- [x] Cada corrida registra EN_CURSO → EXITOSA/FALLIDA, registros y peticiones usadas
- [x] Prueba de integración contra PostgreSQL 16 con las migraciones aplicadas

### ✅ [SL-15](https://github.com/statline-iteso/statline-backend/issues/5) · Validación estricta de métricas contra JSON Schema antes de insertar

**Sprint:** S2 · **Points:** 3 · **Priority:** Alta

**Acceptance criteria**

- [x] Cada línea se valida contra `schemas/<deporte>.schema.json`
- [x] Las líneas inválidas se descartan y se registran sin abortar el partido

### ✅ [SL-16](https://github.com/statline-iteso/statline-backend/issues/6) · CLI por deporte para los CronJob (`ingesta run <deporte>`)

**Sprint:** S2 · **Points:** 3 · **Priority:** Media

**Acceptance criteria**

- [x] `ingesta run basquetbol|americano|futbol [--desde] [--hasta]`; por defecto ayer y hoy (UTC)
- [x] Código de salida ≠ 0 si la corrida falla, para que el Job quede como fallido

### ✅ [SL-17](https://github.com/statline-iteso/statline-backend/issues/7) · Adaptador de Liga MX (api-football, liga 262)

**Sprint:** S4 · **Points:** 5 · **Priority:** Media

**Acceptance criteria**

- [x] `AdaptadorFutbol` implementa `AdaptadorDeporte` con jornada
- [x] Métricas normalizadas válidas contra `futbol.schema.json`
- [ ] Pruebas con fixtures grabados — *cambió: fixtures armados con la documentación de API-Sports, no grabados en vivo: aún no hay API key (D-25)*

### ✅ [SL-18](https://github.com/statline-iteso/statline-backend/issues/8) · Adaptador de NFL (api-american-football, liga 1)

**Sprint:** S4 · **Points:** 5 · **Priority:** Media

**Acceptance criteria**

- [x] `AdaptadorAmericano` implementa `AdaptadorDeporte` con semana como jornada
- [x] Métricas por grupo (pase, carrera, recepción, defensa, pateo) válidas contra `americano.schema.json`
- [ ] Pruebas con fixtures grabados — *cambió: fixtures armados con la documentación de API-Sports, no grabados en vivo: aún no hay API key (D-24)*

### ✅ [SL-19](https://github.com/statline-iteso/statline-backend/issues/9) · Implementar AdaptadorDeporte para consumo de API-Sports en Python

**Sprint:** S2 · **Points:** 8 · **Priority:** Alta

**Acceptance criteria**

- [x] Interfaz `AdaptadorDeporte` con `obtener_partidos()`, `obtener_estadisticas()` y `normalizar()`
- [x] Cliente API-Sports con reintentos (429/5xx), backoff exponencial y tope de cuota diaria
- [x] `AdaptadorBasquetbol` (NBA, liga 12) de punta a punta con normalización en pandas

### ✅ [SL-20](https://github.com/statline-iteso/statline-backend/issues/10) · Proveedores de respaldo: balldontlie.io (NBA) y TheSportsDB (NFL, Liga MX)

**Sprint:** S4 · **Points:** 6 · **Priority:** Media

**Acceptance criteria**

- [x] Si API-Sports falla o agota la cuota, el ejecutor reintenta con el respaldo
- [x] El proveedor usado queda en `ejecucion_ingesta.proveedor`

### ✅ [SL-21](https://github.com/statline-iteso/statline-backend/issues/11) · Dockerfile multi-etapa de ingesta (usuario no root)

**Sprint:** S2 · **Points:** 5 · **Priority:** Media

**Acceptance criteria**

- [x] Etapas deps → test → build → runtime; la etapa `test` corre ruff, mypy y pytest
- [x] Imagen final sin herramientas de build, usuario 10001, `ENTRYPOINT ["ingesta"]`

## E4 · API y modelo de datos

### ✅ [SL-22](https://github.com/statline-iteso/statline-backend/issues/12) · Esqueleto de la API (Node 20, Express, TypeScript) con /healthz, /readyz y /metrics

**Sprint:** S3 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] `createApp(deps)` como raíz de composición; `server.ts` con apagado ordenado en SIGTERM
- [x] /readyz consulta PostgreSQL; /metrics en formato Prometheus
- [x] Manejo central de errores con forma `{ error: { code, message } }`

### ✅ [SL-23](https://github.com/statline-iteso/statline-backend/issues/13) · Esquema Prisma de las 12 entidades con JSONB indexado (GIN)

**Sprint:** S2 · **Points:** 8 · **Priority:** Crítica

**Acceptance criteria**

- [x] 12 entidades del dominio en `schema.prisma` con tablas snake_case
- [x] `metricas` JSONB con índice GIN `jsonb_path_ops`
- [x] Migración inicial y seed de las tres ligas

### ✅ [SL-24](https://github.com/statline-iteso/statline-backend/issues/14) · Autenticación JWT + bcrypt, roles y CRUD de usuarios

**Sprint:** S3 · **Points:** 5 · **Priority:** Crítica

**Acceptance criteria**

- [x] POST /api/auth/login y POST /api/auth/refresh
- [x] Roles ADMIN, ANALISTA y USUARIO; solo ADMIN cambia roles
- [x] /api/usuarios con CRUD estándar; nunca expone el hash

### ✅ [SL-25](https://github.com/statline-iteso/statline-backend/issues/15) · CRUD de ligas y equipos con posiciones, calendario y forma

**Sprint:** S3 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] /api/ligas (?deporte=) con GET /:id/posiciones y GET /:id/calendario
- [x] /api/equipos con GET /:id/forma
- [x] Escrituras restringidas a ADMIN

### ✅ [SL-26](https://github.com/statline-iteso/statline-backend/issues/16) · CRUD de jugadores y partidos con boxscore

**Sprint:** S3 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] /api/jugadores (?q=, ?deporte=) y /api/partidos (?fecha=, ?jornada=)
- [x] GET /api/partidos/:id/boxscore separado por equipo

### ✅ [SL-27](https://github.com/statline-iteso/statline-backend/issues/17) · Crear endpoints de agregación y comparación de atletas (/api/jugadores)

**Sprint:** S4 · **Points:** 5 · **Priority:** Media

**Acceptance criteria**

- [x] GET /api/jugadores/:id/promedios (por temporada, consulta JSONB)
- [x] GET /api/jugadores/:id/tendencia (últimos N partidos)
- [x] GET /api/jugadores/comparar?ids= (2 a 4 jugadores del mismo deporte)

### ✅ [SL-28](https://github.com/statline-iteso/statline-backend/issues/18) · Endpoints de estadísticas y listas de seguimiento

**Sprint:** S4 · **Points:** 5 · **Priority:** Media

**Acceptance criteria**

- [x] /api/estadisticas (?jugadorId=) con CRUD estándar
- [x] /api/listas: POST /:id/elementos y DELETE /:id/elementos/:ref; cada usuario ve solo sus listas

### ✅ [SL-29](https://github.com/statline-iteso/statline-backend/issues/19) · Endpoints de pronósticos, proyecciones y modelos (proxy a predicciones)

**Sprint:** S4 · **Points:** 4 · **Priority:** Media

**Acceptance criteria**

- [x] /api/pronosticos y /api/proyecciones (?jornada=, ?deporte=) con POST /generar y GET /precision
- [x] /api/modelos con POST /:id/activar (uno activo por deporte y tipo) y POST /reentrenar

### ✅ [SL-30](https://github.com/statline-iteso/statline-backend/issues/20) · Endpoints de alertas e ingestas

**Sprint:** S4 · **Points:** 3 · **Priority:** Media

**Acceptance criteria**

- [x] /api/alertas con CRUD estándar por usuario
- [x] /api/ingestas solo GET y DELETE, y POST /ejecutar restringido a ADMIN

### ✅ [SL-31](https://github.com/statline-iteso/statline-backend/issues/21) · Caché y limitación de tasa con Redis

**Sprint:** S5 · **Points:** 3 · **Priority:** Media

**Acceptance criteria**

- [ ] Caché de lecturas frecuentes (posiciones, calendario) con invalidación tras la ingesta — *cambió: se invalida con cada escritura por la API (contador de versión global); lo que escribe la ingesta aparece al vencer el TTL de 60 s (D-16)*
- [ ] Rate limit por IP y por usuario; /readyz incluye Redis — *cambió: límite por IP (global y login); no hay límite por usuario. `/readyz` sí incluye Redis*

## E5 · Servicio de predicciones

### ✅ [SL-32](https://github.com/statline-iteso/statline-backend/issues/22) · Esqueleto del servicio de predicciones (FastAPI) con probes y contrato

**Sprint:** S3 · **Points:** 3 · **Priority:** Alta

**Acceptance criteria**

- [x] /healthz, /readyz (PostgreSQL) y /metrics
- [x] Contrato de entrada validado con Pydantic; rutas pendientes responden 501

### ✅ [SL-33](https://github.com/statline-iteso/statline-backend/issues/23) · Extracción de características desde PostgreSQL

**Sprint:** S4 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] Forma reciente, promedios móviles y localía por equipo
- [x] Promedios móviles por jugador desde `metricas` JSONB

### ✅ [SL-34](https://github.com/statline-iteso/statline-backend/issues/24) · Regresión logística para resultado de partido y marcador esperado

**Sprint:** S4 · **Points:** 8 · **Priority:** Alta

**Acceptance criteria**

- [x] Probabilidades local/empate/visita (empate solo en fútbol)
- [ ] Marcador esperado; comparación contra baseline (siempre gana local) — *cambió: el baseline son las frecuencias de clase del entrenamiento, no «siempre gana local»*

### ✅ [SL-35](https://github.com/statline-iteso/statline-backend/issues/25) · Entrenar modelo de Gradient Boosting para proyección de métricas individuales

**Sprint:** S4 · **Points:** 8 · **Priority:** Alta

**Acceptance criteria**

- [x] Un modelo por métrica principal de cada deporte
- [ ] MAE validado contra baseline (promedio de los últimos 5 partidos) — *cambió: el baseline es el promedio móvil de los últimos 10 partidos, no 5 (D-32)*

### ✅ [SL-36](https://github.com/statline-iteso/statline-backend/issues/26) · Registro de modelos en ModeloPrediccion (versionado y activación)

**Sprint:** S4 · **Points:** 5 · **Priority:** Alta

**Acceptance criteria**

- [x] Artefactos joblib versionados; registro con métrica de error
- [x] Solo un modelo activo por deporte y tipo

### ✅ [SL-37](https://github.com/statline-iteso/statline-backend/issues/27) · Endpoints /generar que escriben PronosticoPartido y ProyeccionJugador

**Sprint:** S4 · **Points:** 4 · **Priority:** Media

**Acceptance criteria**

- [x] POST /pronosticos/generar y /proyecciones/generar usan el modelo activo

### ✅ [SL-38](https://github.com/statline-iteso/statline-backend/issues/28) · Endpoints de precisión y reentrenamiento

**Sprint:** S5 · **Points:** 3 · **Priority:** Media

**Acceptance criteria**

- [x] GET /precision compara pronósticos con resultados finales
- [ ] POST /modelos/reentrenar registra una versión nueva inactiva — *cambió: la versión nueva se activa sola si supera al baseline y al modelo activo (D-31)*

### ✅ [SL-39](https://github.com/statline-iteso/statline-backend/issues/29) · Dockerfile multi-etapa de predicciones y cobertura con pytest

**Sprint:** S3 · **Points:** 2 · **Priority:** Media

**Acceptance criteria**

- [x] Etapa `test` con ruff, mypy y pytest (cobertura ≥ 70 %); runtime no root

## E7 · Pipeline de CI/CD

### ✅ [SL-49](https://github.com/statline-iteso/statline-backend/issues/30) · Workflow ci.yml del backend (lint, tipos, pruebas, integración, imágenes)

**Sprint:** S3 · **Points:** 5 · **Priority:** Crítica

**Acceptance criteria**

- [x] ESLint/Prettier/tsc y ruff/mypy; Jest y pytest con cobertura ≥ 70 %
- [x] Integración contra PostgreSQL efímero con las migraciones aplicadas
- [x] Build multi-etapa de api, predicciones e ingesta

### ✅ [SL-52](https://github.com/statline-iteso/statline-backend/issues/31) · Implementar workflow GitHub Actions con Trivy scanning y fail-gate

**Sprint:** S3 · **Points:** 5 · **Priority:** Crítica

**Acceptance criteria**

- [x] Trivy sobre cada imagen; falla ante hallazgos HIGH o CRITICAL
- [x] Las ramas `develop` y `main` exigen CI verde y una aprobación
