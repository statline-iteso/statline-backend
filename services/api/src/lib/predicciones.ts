import { AppError } from "./errors";

/** What predicciones answered: its status and JSON body, passed through to the client. */
export interface PrediccionesResponse {
  status: number;
  body: unknown;
}

export interface PrediccionesClient {
  get(path: string, query?: Record<string, string>): Promise<PrediccionesResponse>;
  post(path: string, body?: unknown): Promise<PrediccionesResponse>;
}

export interface PrediccionesClientOptions {
  baseUrl: string;
  /** Training can be slow: the default (30 s) is set in config.ts (PREDICCIONES_TIMEOUT_MS). */
  timeoutMs: number;
  fetchImpl?: typeof fetch;
}

/** HTTP client for the predicciones service (cluster-internal). Connection errors and timeouts
 * become 503 PREDICCIONES_UNAVAILABLE; a non-JSON answer becomes 502. */
export function createPrediccionesClient(opts: PrediccionesClientOptions): PrediccionesClient {
  const fetchImpl = opts.fetchImpl ?? fetch;

  async function llamar(
    method: "GET" | "POST",
    path: string,
    init: { query?: Record<string, string>; body?: unknown } = {},
  ): Promise<PrediccionesResponse> {
    const url = new URL(path, opts.baseUrl);
    for (const [clave, valor] of Object.entries(init.query ?? {})) {
      url.searchParams.set(clave, valor);
    }
    let res: Response;
    try {
      res = await fetchImpl(url, {
        method,
        headers: init.body === undefined ? undefined : { "content-type": "application/json" },
        body: init.body === undefined ? undefined : JSON.stringify(init.body),
        signal: AbortSignal.timeout(opts.timeoutMs),
      });
    } catch {
      throw new AppError(
        "PREDICCIONES_UNAVAILABLE",
        503,
        "El servicio de predicciones no responde",
      );
    }
    let body: unknown;
    try {
      body = await res.json();
    } catch {
      throw new AppError(
        "PREDICCIONES_RESPUESTA_INVALIDA",
        502,
        "Respuesta inválida de predicciones",
      );
    }
    return { status: res.status, body };
  }

  return {
    get: (path, query) => llamar("GET", path, { query }),
    post: (path, body) => llamar("POST", path, { body }),
  };
}
