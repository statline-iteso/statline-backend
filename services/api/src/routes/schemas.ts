import { z } from "zod";

export const DeporteSchema = z.enum(["BASQUETBOL", "AMERICANO", "FUTBOL"]);
export const RolSchema = z.enum(["ADMIN", "ANALISTA", "USUARIO"]);
export const EstatusJugadorSchema = z.enum(["DISPONIBLE", "DUDA", "LESIONADO", "SUSPENDIDO"]);
export const EstatusPartidoSchema = z.enum([
  "PROGRAMADO",
  "EN_JUEGO",
  "FINALIZADO",
  "POSPUESTO",
  "CANCELADO",
]);

// ── Usuario ──────────────────────────────────────────────────────────────
export const CreateUsuarioSchema = z.object({
  email: z.string().email(),
  nombre: z.string().min(1).max(120),
  password: z.string().min(8).max(128),
});
export const UpdateUsuarioSchema = z
  .object({
    nombre: z.string().min(1).max(120),
    password: z.string().min(8).max(128),
    rol: RolSchema, // only ADMIN may change it (checked in the router)
  })
  .partial();
export const LoginSchema = z.object({ email: z.string().email(), password: z.string().min(1) });
export const RefreshSchema = z.object({ refreshToken: z.string().min(1) });

// ── Liga ─────────────────────────────────────────────────────────────────
export const CreateLigaSchema = z.object({
  nombre: z.string().min(1),
  deporte: DeporteSchema,
  pais: z.string().optional(),
  temporada: z.string().min(1),
  proveedor: z.string().default("api-sports"),
  proveedorLigaId: z.string().min(1),
  activa: z.boolean().default(true),
});
export const UpdateLigaSchema = CreateLigaSchema.partial();
export const LigaFilterSchema = z.object({ deporte: DeporteSchema.optional() });

// ── Equipo ───────────────────────────────────────────────────────────────
export const CreateEquipoSchema = z.object({
  ligaId: z.string().uuid(),
  nombre: z.string().min(1),
  abreviatura: z.string().max(10).optional(),
  conferencia: z.string().optional(),
  ciudad: z.string().optional(),
  logoUrl: z.string().url().optional(),
  proveedorId: z.string().min(1),
});
export const UpdateEquipoSchema = CreateEquipoSchema.partial();
export const EquipoFilterSchema = z.object({}).passthrough();

// ── Jugador ──────────────────────────────────────────────────────────────
export const CreateJugadorSchema = z.object({
  equipoId: z.string().uuid().nullable().optional(),
  deporte: DeporteSchema,
  nombre: z.string().min(1),
  posicion: z.string().optional(),
  numero: z.number().int().min(0).max(99).optional(),
  estatus: EstatusJugadorSchema.default("DISPONIBLE"),
  proveedorId: z.string().min(1),
});
export const UpdateJugadorSchema = CreateJugadorSchema.partial();
export const JugadorFilterSchema = z.object({
  q: z.string().min(1).optional(),
  deporte: DeporteSchema.optional(),
});

// ── Partido ──────────────────────────────────────────────────────────────
export const CreatePartidoSchema = z.object({
  ligaId: z.string().uuid(),
  localId: z.string().uuid(),
  visitaId: z.string().uuid(),
  fecha: z.coerce.date(),
  jornada: z.number().int().positive().optional(),
  temporada: z.string().min(1),
  estatus: EstatusPartidoSchema.default("PROGRAMADO"),
  marcadorLocal: z.number().int().min(0).optional(),
  marcadorVisita: z.number().int().min(0).optional(),
  proveedorId: z.string().min(1),
});
export const UpdatePartidoSchema = CreatePartidoSchema.partial();
export const PartidoFilterSchema = z.object({
  fecha: z
    .string()
    .regex(/^\d{4}-\d{2}-\d{2}$/, "Formato YYYY-MM-DD")
    .optional(),
  jornada: z.coerce.number().int().positive().optional(),
});

// ── Jugador · agregados (SL-27) ──────────────────────────────────────────
export const PromediosQuerySchema = z.object({
  ultimos: z.coerce.number().int().min(1).max(500).optional(),
});
export const TendenciaQuerySchema = z.object({
  metrica: z.string().min(1).max(100),
  n: z.coerce.number().int().min(1).max(100).default(10),
});
export const CompararQuerySchema = z.object({
  ids: z
    .string()
    .transform((s) =>
      s
        .split(",")
        .map((id) => id.trim())
        .filter((id) => id.length > 0),
    )
    .pipe(
      z
        .array(z.string().uuid())
        .min(2)
        .max(4)
        .refine((ids) => new Set(ids).size === ids.length, "Los ids no pueden repetirse"),
    ),
});

// ── EstadisticaJugadorPartido ────────────────────────────────────────────
// The sport is not an input: it is taken from the partido's liga, so a client can't send
// metrics for one sport tagged as another.
export const CreateEstadisticaSchema = z.object({
  partidoId: z.string().uuid(),
  jugadorId: z.string().uuid(),
  equipoId: z.string().uuid(),
  minutos: z.number().int().min(0).nullish(),
  metricas: z.record(z.string(), z.unknown()),
});
export const UpdateEstadisticaSchema = CreateEstadisticaSchema.partial();
export const EstadisticaFilterSchema = z.object({
  jugadorId: z.string().uuid().optional(),
  partidoId: z.string().uuid().optional(),
});
/** Upper bound for POST /api/estadisticas/lote (one transaction). */
export const MAX_LOTE = 500;
export const LoteSchema = z.array(z.unknown()).min(1).max(MAX_LOTE);

// ── ListaSeguimiento ─────────────────────────────────────────────────────
export const CreateListaSchema = z.object({ nombre: z.string().min(1).max(120) });
export const UpdateListaSchema = CreateListaSchema.partial();
export const ElementoListaSchema = z.object({
  tipo: z.enum(["JUGADOR", "EQUIPO"]),
  refId: z.string().uuid(),
});
// ── Alerta ───────────────────────────────────────────────────────────────
export const OperadorSchema = z.enum([">", ">=", "<", "<=", "="]);
export const CondicionSchema = z.object({
  metrica: z.string().min(1),
  operador: OperadorSchema,
  valor: z.number(),
});

const ActivaField = { activa: z.boolean().optional() };

const LesionSchema = z.object({
  tipo: z.literal("LESION"),
  jugadorId: z.string().uuid(),
  ...ActivaField,
});
const InicioPartidoSchema = z.object({
  tipo: z.literal("INICIO_PARTIDO"),
  jugadorId: z.string().uuid().optional(),
  equipoId: z.string().uuid().optional(),
  ...ActivaField,
});
const UmbralSchema = z.object({
  tipo: z.literal("UMBRAL"),
  jugadorId: z.string().uuid(),
  condicion: CondicionSchema,
  ...ActivaField,
});

/** Discriminated on `tipo`: LESION and UMBRAL need a jugador, INICIO_PARTIDO a jugador or equipo. */
export const CreateAlertaSchema = z
  .discriminatedUnion("tipo", [LesionSchema, InicioPartidoSchema, UmbralSchema])
  .superRefine((alerta, ctx) => {
    if (alerta.tipo === "INICIO_PARTIDO" && !alerta.jugadorId && !alerta.equipoId) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: "INICIO_PARTIDO requiere jugadorId o equipoId",
        path: ["jugadorId"],
      });
    }
  });

/** PUT accepts either only `{activa}` (toggle) or a full alerta definition that replaces it. */
export const ActivaAlertaSchema = z.object({ activa: z.boolean() }).strict();
export const UpdateAlertaSchema = z.union([ActivaAlertaSchema, CreateAlertaSchema]);

// ── EjecucionIngesta ─────────────────────────────────────────────────────
export const EstatusIngestaSchema = z.enum(["EN_CURSO", "EXITOSA", "FALLIDA"]);
export const IngestaFilterSchema = z.object({
  deporte: DeporteSchema.optional(),
  estatus: EstatusIngestaSchema.optional(),
});
export const EjecutarIngestaSchema = z.object({ deporte: DeporteSchema });

// ── Predicciones (SL-29) ─────────────────────────────────────────────────
export const TipoInferenciaSchema = z.enum(["RESULTADO_PARTIDO", "PROYECCION_JUGADOR"]);
const JornadaSchema = z.coerce.number().int().positive();

export const PronosticoFilterSchema = z.object({
  deporte: DeporteSchema.optional(),
  jornada: JornadaSchema.optional(),
  partidoId: z.string().uuid().optional(),
});
export const ProyeccionFilterSchema = z.object({
  deporte: DeporteSchema.optional(),
  jornada: JornadaSchema.optional(),
  jugadorId: z.string().uuid().optional(),
  partidoId: z.string().uuid().optional(),
});
export const ModeloFilterSchema = z.object({
  deporte: DeporteSchema.optional(),
  tipo: TipoInferenciaSchema.optional(),
});
export const GenerarPronosticosSchema = z.object({
  deporte: DeporteSchema,
  jornada: z.number().int().positive().optional(),
  partidoIds: z.array(z.string().uuid()).max(200).optional(),
});
export const GenerarProyeccionesSchema = z.object({
  deporte: DeporteSchema,
  jornada: z.number().int().positive().optional(),
  jugadorIds: z.array(z.string().uuid()).max(500).optional(),
});
export const ReentrenarSchema = z.object({ deporte: DeporteSchema, tipo: TipoInferenciaSchema });
/** GET /precision: the tipo is fixed per router (pronosticos vs proyecciones). */
export const precisionSchema = <T extends string>(tipo: T) =>
  z.object({ deporte: DeporteSchema, tipo: z.literal(tipo).default(tipo) });
