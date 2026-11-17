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
