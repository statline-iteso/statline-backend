import { readFileSync } from "fs";
import { request } from "https";
import { z } from "zod";

/** Minimal Kubernetes REST client for in-cluster calls (no extra npm dependency). */
export interface K8sRequest {
  method: "GET" | "POST";
  path: string;
  body?: unknown;
}
export interface K8sResponse {
  status: number;
  body: unknown;
}
export type K8sHttp = (req: K8sRequest) => Promise<K8sResponse>;

export const SERVICEACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount";

export interface InClusterOptions {
  env?: NodeJS.ProcessEnv;
  /** Reads a file as UTF-8; injected so tests need no real service account. */
  readFile?: (path: string) => string;
  dir?: string;
}

const ServiceAccountEnv = z.object({
  KUBERNETES_SERVICE_HOST: z.string().min(1),
  KUBERNETES_SERVICE_PORT: z.string().min(1).default("443"),
});

/**
 * Builds an HTTPS client for the API server from the pod's service account. The CA is read once,
 * the token on every call (projected tokens rotate). Node's fetch cannot take a custom CA without
 * undici, so the https module is used.
 */
export function crearClienteEnCluster(opts: InClusterOptions = {}): {
  http: K8sHttp;
  namespace: string;
} {
  const env = ServiceAccountEnv.parse(opts.env ?? process.env);
  const dir = opts.dir ?? SERVICEACCOUNT_DIR;
  const readFile = opts.readFile ?? ((path: string) => readFileSync(path, "utf8"));
  const ca = readFile(`${dir}/ca.crt`);
  const namespace = readFile(`${dir}/namespace`).trim();
  const host = env.KUBERNETES_SERVICE_HOST;
  const port = Number(env.KUBERNETES_SERVICE_PORT);

  const http: K8sHttp = ({ method, path, body }) =>
    new Promise<K8sResponse>((resolve, reject) => {
      const token = readFile(`${dir}/token`).trim();
      const payload = body === undefined ? undefined : JSON.stringify(body);
      const req = request(
        {
          host,
          port,
          method,
          path,
          ca,
          timeout: 10_000,
          headers: {
            Authorization: `Bearer ${token}`,
            Accept: "application/json",
            ...(payload === undefined
              ? {}
              : {
                  "Content-Type": "application/json",
                  "Content-Length": Buffer.byteLength(payload),
                }),
          },
        },
        (res) => {
          const chunks: Buffer[] = [];
          res.on("data", (chunk: Buffer) => chunks.push(chunk));
          res.on("end", () => {
            const text = Buffer.concat(chunks).toString("utf8");
            let parsed: unknown = undefined;
            try {
              parsed = text ? JSON.parse(text) : undefined;
            } catch {
              parsed = text;
            }
            resolve({ status: res.statusCode ?? 0, body: parsed });
          });
        },
      );
      req.on("timeout", () => req.destroy(new Error("Kubernetes API timeout")));
      req.on("error", reject);
      if (payload !== undefined) req.write(payload);
      req.end();
    });

  if (!namespace) throw new Error("Service account sin namespace");
  return { http, namespace };
}
