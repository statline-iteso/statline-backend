import type { Deporte } from "@prisma/client";
import { z } from "zod";
import { AppError } from "./errors";
import { crearClienteEnCluster, type K8sHttp } from "./k8s";

/**
 * Starts one manual ingestion run for a sport. Two implementations, chosen by INGESTA_LANZADOR:
 * `deshabilitado` (default, answers 503) and `kubernetes` (creates a Job from the CronJob).
 */
export interface LanzadorIngesta {
  lanzar(deporte: Deporte): Promise<{ job: string }>;
}

export const CRONJOB_POR_DEPORTE: Record<Deporte, string> = {
  BASQUETBOL: "ingesta-basquetbol",
  AMERICANO: "ingesta-americano",
  FUTBOL: "ingesta-futbol",
};

export function crearLanzadorDeshabilitado(): LanzadorIngesta {
  return {
    lanzar: async () => {
      throw new AppError(
        "NOT_CONFIGURED",
        503,
        "La ejecución manual de ingestas no está configurada (INGESTA_LANZADOR)",
      );
    },
  };
}

const CronJobSchema = z.object({
  metadata: z.object({
    name: z.string().min(1),
    uid: z.string().min(1),
    labels: z.record(z.string()).optional(),
  }),
  spec: z.object({
    jobTemplate: z.object({
      metadata: z
        .object({
          labels: z.record(z.string()).optional(),
          annotations: z.record(z.string()).optional(),
        })
        .optional(),
      spec: z.record(z.unknown()),
    }),
  }),
});
export type CronJobManifest = z.infer<typeof CronJobSchema>;

/** Job manual a partir de spec.jobTemplate, con ownerReference al CronJob (pura, testeable). */
export function construirJobManual(
  cron: CronJobManifest,
  deporte: Deporte,
  ahora: number,
): { apiVersion: "batch/v1"; kind: "Job"; metadata: Record<string, unknown>; spec: unknown } {
  const plantilla = cron.spec.jobTemplate;
  const name = `${cron.metadata.name}-manual-${ahora}`;
  return {
    apiVersion: "batch/v1",
    kind: "Job",
    metadata: {
      name,
      labels: {
        ...plantilla.metadata?.labels,
        "statline/origen": "manual",
        "statline/deporte": deporte.toLowerCase(),
      },
      annotations: {
        ...plantilla.metadata?.annotations,
        "cronjob.kubernetes.io/instantiate": "manual",
      },
      ownerReferences: [
        {
          apiVersion: "batch/v1",
          kind: "CronJob",
          name: cron.metadata.name,
          uid: cron.metadata.uid,
          controller: false,
          blockOwnerDeletion: false,
        },
      ],
    },
    spec: plantilla.spec,
  };
}

export interface LanzadorKubernetesDeps {
  http: K8sHttp;
  namespace: string;
  ahora?: () => number;
}

export function crearLanzadorKubernetes({
  http,
  namespace,
  ahora = Date.now,
}: LanzadorKubernetesDeps): LanzadorIngesta {
  const base = `/apis/batch/v1/namespaces/${encodeURIComponent(namespace)}`;
  return {
    async lanzar(deporte) {
      const cronName = CRONJOB_POR_DEPORTE[deporte];
      const llamar: K8sHttp = async (req) => {
        try {
          return await http(req);
        } catch {
          throw new AppError("K8S_ERROR", 503, "Kubernetes no está disponible");
        }
      };
      const cronRes = await llamar({ method: "GET", path: `${base}/cronjobs/${cronName}` });
      if (cronRes.status === 404) {
        throw new AppError("NOT_CONFIGURED", 503, `CronJob ${cronName} no existe`);
      }
      if (cronRes.status !== 200) throw new AppError("K8S_ERROR", 503, "Kubernetes no respondió");

      const parsed = CronJobSchema.safeParse(cronRes.body);
      if (!parsed.success) {
        throw new AppError("K8S_ERROR", 503, "Respuesta inesperada del CronJob");
      }
      const job = construirJobManual(parsed.data, deporte, ahora());
      const jobRes = await llamar({ method: "POST", path: `${base}/jobs`, body: job });
      if (jobRes.status !== 201 && jobRes.status !== 200) {
        throw new AppError("K8S_ERROR", 503, "Kubernetes rechazó crear el Job");
      }
      return { job: job.metadata.name as string };
    },
  };
}

export type ModoLanzador = "deshabilitado" | "kubernetes";

export function crearLanzadorIngesta(
  modo: ModoLanzador,
  opts: Parameters<typeof crearClienteEnCluster>[0] = {},
): LanzadorIngesta {
  if (modo === "deshabilitado") return crearLanzadorDeshabilitado();
  const { http, namespace } = crearClienteEnCluster(opts);
  return crearLanzadorKubernetes({ http, namespace });
}
