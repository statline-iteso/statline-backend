-- CreateEnum
CREATE TYPE "deporte" AS ENUM ('BASQUETBOL', 'AMERICANO', 'FUTBOL');

-- CreateEnum
CREATE TYPE "rol" AS ENUM ('ADMIN', 'ANALISTA', 'USUARIO');

-- CreateEnum
CREATE TYPE "estatus_jugador" AS ENUM ('DISPONIBLE', 'DUDA', 'LESIONADO', 'SUSPENDIDO');

-- CreateEnum
CREATE TYPE "estatus_partido" AS ENUM ('PROGRAMADO', 'EN_JUEGO', 'FINALIZADO', 'POSPUESTO', 'CANCELADO');

-- CreateEnum
CREATE TYPE "tipo_inferencia" AS ENUM ('RESULTADO_PARTIDO', 'PROYECCION_JUGADOR');

-- CreateEnum
CREATE TYPE "tipo_alerta" AS ENUM ('LESION', 'UMBRAL', 'INICIO_PARTIDO');

-- CreateEnum
CREATE TYPE "tipo_elemento" AS ENUM ('JUGADOR', 'EQUIPO');

-- CreateEnum
CREATE TYPE "estatus_ingesta" AS ENUM ('EN_CURSO', 'EXITOSA', 'FALLIDA');

-- CreateTable
CREATE TABLE "usuario" (
    "id" UUID NOT NULL,
    "email" TEXT NOT NULL,
    "nombre" TEXT NOT NULL,
    "password_hash" TEXT NOT NULL,
    "rol" "rol" NOT NULL DEFAULT 'USUARIO',
    "creado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "actualizado_en" TIMESTAMP(3) NOT NULL,

    CONSTRAINT "usuario_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "liga" (
    "id" UUID NOT NULL,
    "nombre" TEXT NOT NULL,
    "deporte" "deporte" NOT NULL,
    "pais" TEXT,
    "temporada" TEXT NOT NULL,
    "proveedor" TEXT NOT NULL DEFAULT 'api-sports',
    "proveedor_liga_id" TEXT NOT NULL,
    "activa" BOOLEAN NOT NULL DEFAULT true,
    "creado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "liga_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "equipo" (
    "id" UUID NOT NULL,
    "liga_id" UUID NOT NULL,
    "nombre" TEXT NOT NULL,
    "abreviatura" TEXT,
    "conferencia" TEXT,
    "ciudad" TEXT,
    "logo_url" TEXT,
    "forma_reciente" TEXT,
    "proveedor_id" TEXT NOT NULL,

    CONSTRAINT "equipo_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "jugador" (
    "id" UUID NOT NULL,
    "equipo_id" UUID,
    "deporte" "deporte" NOT NULL,
    "nombre" TEXT NOT NULL,
    "posicion" TEXT,
    "numero" INTEGER,
    "estatus" "estatus_jugador" NOT NULL DEFAULT 'DISPONIBLE',
    "proveedor_id" TEXT NOT NULL,
    "actualizado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "jugador_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "partido" (
    "id" UUID NOT NULL,
    "liga_id" UUID NOT NULL,
    "local_id" UUID NOT NULL,
    "visita_id" UUID NOT NULL,
    "fecha" TIMESTAMP(3) NOT NULL,
    "jornada" INTEGER,
    "temporada" TEXT NOT NULL,
    "estatus" "estatus_partido" NOT NULL DEFAULT 'PROGRAMADO',
    "marcador_local" INTEGER,
    "marcador_visita" INTEGER,
    "proveedor_id" TEXT NOT NULL,

    CONSTRAINT "partido_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "estadistica_jugador_partido" (
    "id" UUID NOT NULL,
    "partido_id" UUID NOT NULL,
    "jugador_id" UUID NOT NULL,
    "equipo_id" UUID NOT NULL,
    "deporte" "deporte" NOT NULL,
    "minutos" INTEGER,
    "metricas" JSONB NOT NULL,
    "creado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "estadistica_jugador_partido_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "lista_seguimiento" (
    "id" UUID NOT NULL,
    "usuario_id" UUID NOT NULL,
    "nombre" TEXT NOT NULL,
    "creado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "lista_seguimiento_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "elemento_lista" (
    "id" UUID NOT NULL,
    "lista_id" UUID NOT NULL,
    "tipo" "tipo_elemento" NOT NULL,
    "ref_id" UUID NOT NULL,

    CONSTRAINT "elemento_lista_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "pronostico_partido" (
    "id" UUID NOT NULL,
    "partido_id" UUID NOT NULL,
    "modelo_id" UUID NOT NULL,
    "prob_local" DOUBLE PRECISION NOT NULL,
    "prob_empate" DOUBLE PRECISION NOT NULL,
    "prob_visita" DOUBLE PRECISION NOT NULL,
    "marcador_esperado_local" DOUBLE PRECISION,
    "marcador_esperado_visita" DOUBLE PRECISION,
    "generado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "pronostico_partido_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "proyeccion_jugador" (
    "id" UUID NOT NULL,
    "jugador_id" UUID NOT NULL,
    "partido_id" UUID NOT NULL,
    "modelo_id" UUID NOT NULL,
    "metricas" JSONB NOT NULL,
    "generado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "proyeccion_jugador_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "modelo_prediccion" (
    "id" UUID NOT NULL,
    "deporte" "deporte" NOT NULL,
    "tipo" "tipo_inferencia" NOT NULL,
    "version" TEXT NOT NULL,
    "artefacto_uri" TEXT NOT NULL,
    "nombre_metrica" TEXT NOT NULL,
    "metrica_error" DOUBLE PRECISION NOT NULL,
    "activo" BOOLEAN NOT NULL DEFAULT false,
    "entrenado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "modelo_prediccion_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "alerta" (
    "id" UUID NOT NULL,
    "usuario_id" UUID NOT NULL,
    "tipo" "tipo_alerta" NOT NULL,
    "jugador_id" UUID,
    "equipo_id" UUID,
    "condicion" JSONB,
    "activa" BOOLEAN NOT NULL DEFAULT true,
    "ultima_disparada" TIMESTAMP(3),
    "creado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "alerta_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ejecucion_ingesta" (
    "id" UUID NOT NULL,
    "deporte" "deporte" NOT NULL,
    "proveedor" TEXT NOT NULL,
    "estatus" "estatus_ingesta" NOT NULL DEFAULT 'EN_CURSO',
    "iniciada_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "finalizada_en" TIMESTAMP(3),
    "registros_procesados" INTEGER NOT NULL DEFAULT 0,
    "peticiones_usadas" INTEGER NOT NULL DEFAULT 0,
    "error" TEXT,

    CONSTRAINT "ejecucion_ingesta_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "usuario_email_key" ON "usuario"("email");

-- CreateIndex
CREATE INDEX "liga_deporte_idx" ON "liga"("deporte");

-- CreateIndex
CREATE UNIQUE INDEX "liga_proveedor_proveedor_liga_id_temporada_key" ON "liga"("proveedor", "proveedor_liga_id", "temporada");

-- CreateIndex
CREATE UNIQUE INDEX "equipo_liga_id_proveedor_id_key" ON "equipo"("liga_id", "proveedor_id");

-- CreateIndex
CREATE INDEX "jugador_nombre_idx" ON "jugador"("nombre");

-- CreateIndex
CREATE UNIQUE INDEX "jugador_deporte_proveedor_id_key" ON "jugador"("deporte", "proveedor_id");

-- CreateIndex
CREATE INDEX "partido_fecha_idx" ON "partido"("fecha");

-- CreateIndex
CREATE INDEX "partido_liga_id_jornada_idx" ON "partido"("liga_id", "jornada");

-- CreateIndex
CREATE UNIQUE INDEX "partido_liga_id_proveedor_id_key" ON "partido"("liga_id", "proveedor_id");

-- CreateIndex
CREATE INDEX "estadistica_jugador_partido_jugador_id_idx" ON "estadistica_jugador_partido"("jugador_id");

-- CreateIndex
CREATE INDEX "estadistica_jugador_partido_metricas_idx" ON "estadistica_jugador_partido" USING GIN ("metricas" jsonb_path_ops);

-- CreateIndex
CREATE UNIQUE INDEX "estadistica_jugador_partido_partido_id_jugador_id_key" ON "estadistica_jugador_partido"("partido_id", "jugador_id");

-- CreateIndex
CREATE INDEX "lista_seguimiento_usuario_id_idx" ON "lista_seguimiento"("usuario_id");

-- CreateIndex
CREATE UNIQUE INDEX "elemento_lista_lista_id_tipo_ref_id_key" ON "elemento_lista"("lista_id", "tipo", "ref_id");

-- CreateIndex
CREATE INDEX "pronostico_partido_partido_id_idx" ON "pronostico_partido"("partido_id");

-- CreateIndex
CREATE INDEX "proyeccion_jugador_jugador_id_partido_id_idx" ON "proyeccion_jugador"("jugador_id", "partido_id");

-- CreateIndex
CREATE INDEX "modelo_prediccion_deporte_tipo_activo_idx" ON "modelo_prediccion"("deporte", "tipo", "activo");

-- CreateIndex
CREATE UNIQUE INDEX "modelo_prediccion_deporte_tipo_version_key" ON "modelo_prediccion"("deporte", "tipo", "version");

-- CreateIndex
CREATE INDEX "alerta_usuario_id_idx" ON "alerta"("usuario_id");

-- CreateIndex
CREATE INDEX "ejecucion_ingesta_deporte_iniciada_en_idx" ON "ejecucion_ingesta"("deporte", "iniciada_en");

-- AddForeignKey
ALTER TABLE "equipo" ADD CONSTRAINT "equipo_liga_id_fkey" FOREIGN KEY ("liga_id") REFERENCES "liga"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "jugador" ADD CONSTRAINT "jugador_equipo_id_fkey" FOREIGN KEY ("equipo_id") REFERENCES "equipo"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "partido" ADD CONSTRAINT "partido_liga_id_fkey" FOREIGN KEY ("liga_id") REFERENCES "liga"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "partido" ADD CONSTRAINT "partido_local_id_fkey" FOREIGN KEY ("local_id") REFERENCES "equipo"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "partido" ADD CONSTRAINT "partido_visita_id_fkey" FOREIGN KEY ("visita_id") REFERENCES "equipo"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "estadistica_jugador_partido" ADD CONSTRAINT "estadistica_jugador_partido_partido_id_fkey" FOREIGN KEY ("partido_id") REFERENCES "partido"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "estadistica_jugador_partido" ADD CONSTRAINT "estadistica_jugador_partido_jugador_id_fkey" FOREIGN KEY ("jugador_id") REFERENCES "jugador"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "estadistica_jugador_partido" ADD CONSTRAINT "estadistica_jugador_partido_equipo_id_fkey" FOREIGN KEY ("equipo_id") REFERENCES "equipo"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "lista_seguimiento" ADD CONSTRAINT "lista_seguimiento_usuario_id_fkey" FOREIGN KEY ("usuario_id") REFERENCES "usuario"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "elemento_lista" ADD CONSTRAINT "elemento_lista_lista_id_fkey" FOREIGN KEY ("lista_id") REFERENCES "lista_seguimiento"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "pronostico_partido" ADD CONSTRAINT "pronostico_partido_partido_id_fkey" FOREIGN KEY ("partido_id") REFERENCES "partido"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "pronostico_partido" ADD CONSTRAINT "pronostico_partido_modelo_id_fkey" FOREIGN KEY ("modelo_id") REFERENCES "modelo_prediccion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "proyeccion_jugador" ADD CONSTRAINT "proyeccion_jugador_jugador_id_fkey" FOREIGN KEY ("jugador_id") REFERENCES "jugador"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "proyeccion_jugador" ADD CONSTRAINT "proyeccion_jugador_partido_id_fkey" FOREIGN KEY ("partido_id") REFERENCES "partido"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "proyeccion_jugador" ADD CONSTRAINT "proyeccion_jugador_modelo_id_fkey" FOREIGN KEY ("modelo_id") REFERENCES "modelo_prediccion"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "alerta" ADD CONSTRAINT "alerta_usuario_id_fkey" FOREIGN KEY ("usuario_id") REFERENCES "usuario"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "alerta" ADD CONSTRAINT "alerta_jugador_id_fkey" FOREIGN KEY ("jugador_id") REFERENCES "jugador"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "alerta" ADD CONSTRAINT "alerta_equipo_id_fkey" FOREIGN KEY ("equipo_id") REFERENCES "equipo"("id") ON DELETE CASCADE ON UPDATE CASCADE;

