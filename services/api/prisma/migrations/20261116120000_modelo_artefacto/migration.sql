-- CreateTable
CREATE TABLE "modelo_artefacto" (
    "id" UUID NOT NULL,
    "modelo_id" UUID NOT NULL,
    "contenido" BYTEA NOT NULL,
    "sha256" TEXT NOT NULL,
    "tamano_bytes" INTEGER NOT NULL,
    "creado_en" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "modelo_artefacto_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "modelo_artefacto_modelo_id_key" ON "modelo_artefacto"("modelo_id");

-- AddForeignKey
ALTER TABLE "modelo_artefacto" ADD CONSTRAINT "modelo_artefacto_modelo_id_fkey" FOREIGN KEY ("modelo_id") REFERENCES "modelo_prediccion"("id") ON DELETE CASCADE ON UPDATE CASCADE;

