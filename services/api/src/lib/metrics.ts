import client from "prom-client";

export function createMetrics() {
  const registry = new client.Registry();
  client.collectDefaultMetrics({ register: registry });
  const httpRequests = new client.Counter({
    name: "statline_http_requests_total",
    help: "HTTP requests by method, route and status",
    labelNames: ["method", "route", "status"] as const,
    registers: [registry],
  });
  const httpDuration = new client.Histogram({
    name: "statline_http_request_duration_seconds",
    help: "HTTP request duration in seconds",
    labelNames: ["method", "route"] as const,
    buckets: [0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5],
    registers: [registry],
  });
  return { registry, httpRequests, httpDuration };
}

export type Metrics = ReturnType<typeof createMetrics>;
