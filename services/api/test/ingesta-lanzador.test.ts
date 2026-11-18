import request from "supertest";
import { bearer } from "./helpers";
import { buildAppWithLanzador } from "./ingestas-helpers";
import {
  CRONJOB_POR_DEPORTE,
  construirJobManual,
  crearLanzadorIngesta,
  crearLanzadorKubernetes,
  type CronJobManifest,
} from "../src/lib/ingesta-lanzador";
import type { K8sHttp, K8sRequest } from "../src/lib/k8s";

const NS = "statline-dev";
const base = `/apis/batch/v1/namespaces/${NS}`;

const cronJob = (name: string) => ({
  apiVersion: "batch/v1",
  kind: "CronJob",
  metadata: { name, namespace: NS, uid: "uid-123", labels: { app: "ingesta" } },
  spec: {
    schedule: "0 8 * * *",
    jobTemplate: {
      metadata: { labels: { app: "ingesta" }, annotations: { nota: "x" } },
      spec: { backoffLimit: 2, template: { spec: { restartPolicy: "Never" } } },
    },
  },
});

/** Fake API server: serves the CronJob with GET and answers the POST with the given status. */
function fakeK8s(opts: { cronStatus?: number; jobStatus?: number } = {}) {
  const calls: K8sRequest[] = [];
  const http: K8sHttp = async (req) => {
    calls.push(req);
    if (req.method === "GET") {
      const name = req.path.split("/").pop() ?? "";
      if (opts.cronStatus && opts.cronStatus !== 200) {
        return { status: opts.cronStatus, body: { kind: "Status" } };
      }
      return { status: 200, body: cronJob(name) };
    }
    return { status: opts.jobStatus ?? 201, body: req.body };
  };
  return { http, calls };
}

describe("crearLanzadorKubernetes", () => {
  it("GETs the CronJob for the sport and POSTs a Job built from its jobTemplate", async () => {
    const { http, calls } = fakeK8s();
    const lanzador = crearLanzadorKubernetes({ http, namespace: NS, ahora: () => 1700000000000 });

    const res = await lanzador.lanzar("FUTBOL");

    expect(res).toEqual({ job: "ingesta-futbol-manual-1700000000000" });
    expect(calls[0]).toEqual({ method: "GET", path: `${base}/cronjobs/ingesta-futbol` });
    expect(calls[1]).toMatchObject({ method: "POST", path: `${base}/jobs` });
    expect(calls[1]?.body).toEqual({
      apiVersion: "batch/v1",
      kind: "Job",
      metadata: {
        name: "ingesta-futbol-manual-1700000000000",
        labels: { app: "ingesta", "statline/origen": "manual", "statline/deporte": "futbol" },
        annotations: { nota: "x", "cronjob.kubernetes.io/instantiate": "manual" },
        ownerReferences: [
          {
            apiVersion: "batch/v1",
            kind: "CronJob",
            name: "ingesta-futbol",
            uid: "uid-123",
            controller: false,
            blockOwnerDeletion: false,
          },
        ],
      },
      spec: { backoffLimit: 2, template: { spec: { restartPolicy: "Never" } } },
    });
  });

  it("maps network failures to 503 K8S_ERROR", async () => {
    const lanzador = crearLanzadorKubernetes({
      http: async () => {
        throw new Error("ECONNREFUSED");
      },
      namespace: NS,
    });
    await expect(lanzador.lanzar("FUTBOL")).rejects.toMatchObject({
      status: 503,
      code: "K8S_ERROR",
    });
  });

  it("maps each sport to its CronJob", () => {
    expect(CRONJOB_POR_DEPORTE).toEqual({
      BASQUETBOL: "ingesta-basquetbol",
      AMERICANO: "ingesta-americano",
      FUTBOL: "ingesta-futbol",
    });
  });

  it("answers 503 NOT_CONFIGURED when the CronJob does not exist", async () => {
    const { http } = fakeK8s({ cronStatus: 404 });
    const lanzador = crearLanzadorKubernetes({ http, namespace: NS });
    await expect(lanzador.lanzar("AMERICANO")).rejects.toMatchObject({
      status: 503,
      code: "NOT_CONFIGURED",
    });
  });

  it("answers 503 K8S_ERROR when the API server fails or the CronJob has an unexpected shape", async () => {
    const forbidden = crearLanzadorKubernetes({
      http: fakeK8s({ cronStatus: 403 }).http,
      namespace: NS,
    });
    await expect(forbidden.lanzar("FUTBOL")).rejects.toMatchObject({
      status: 503,
      code: "K8S_ERROR",
    });

    const malformed: K8sHttp = async () => ({ status: 200, body: { metadata: {} } });
    await expect(
      crearLanzadorKubernetes({ http: malformed, namespace: NS }).lanzar("FUTBOL"),
    ).rejects.toMatchObject({ status: 503, code: "K8S_ERROR" });
  });

  it("answers 503 K8S_ERROR when the Job is rejected", async () => {
    const { http } = fakeK8s({ jobStatus: 403 });
    const lanzador = crearLanzadorKubernetes({ http, namespace: NS });
    await expect(lanzador.lanzar("BASQUETBOL")).rejects.toMatchObject({
      status: 503,
      code: "K8S_ERROR",
    });
  });

  it("the route answers 202 with the job name using the kubernetes implementation", async () => {
    const { http } = fakeK8s();
    const lanzador = crearLanzadorKubernetes({ http, namespace: NS, ahora: () => 42 });
    const { app } = buildAppWithLanzador(lanzador);
    const res = await request(app)
      .post("/api/ingestas/ejecutar")
      .set("Authorization", bearer("ADMIN"))
      .send({ deporte: "BASQUETBOL" });
    expect(res.status).toBe(202);
    expect(res.body).toEqual({ job: "ingesta-basquetbol-manual-42" });
  });
});

describe("construirJobManual", () => {
  it("works without template labels or annotations", () => {
    const cron: CronJobManifest = {
      metadata: { name: "ingesta-americano", uid: "u" },
      spec: { jobTemplate: { spec: {} } },
    };
    const job = construirJobManual(cron, "AMERICANO", 7);
    expect(job.metadata.name).toBe("ingesta-americano-manual-7");
    expect(job.metadata.labels).toEqual({
      "statline/origen": "manual",
      "statline/deporte": "americano",
    });
  });
});

describe("crearLanzadorIngesta", () => {
  it("returns the disabled launcher by default and never touches the cluster", async () => {
    const lanzador = crearLanzadorIngesta("deshabilitado");
    await expect(lanzador.lanzar("FUTBOL")).rejects.toMatchObject({ status: 503 });
  });

  it("builds the in-cluster client for kubernetes mode from the service account files", async () => {
    const files: Record<string, string> = {
      "/sa/ca.crt": "CA",
      "/sa/namespace": "statline-prod\n",
    };
    const lanzador = crearLanzadorIngesta("kubernetes", {
      env: { KUBERNETES_SERVICE_HOST: "10.0.0.1" },
      dir: "/sa",
      readFile: (p) => {
        const v = files[p];
        if (v === undefined) throw new Error(`no file ${p}`);
        return v;
      },
    });
    expect(lanzador).toHaveProperty("lanzar");
  });
});
