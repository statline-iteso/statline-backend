import * as Sentry from "@sentry/node";

/**
 * Sentry error monitoring (statline-infra D-43). Imported first by server.ts, before express and
 * http load, so the SDK can instrument them. Off without SENTRY_DSN: local runs, tests and k3d
 * send nothing.
 *
 * - SENTRY_ENVIRONMENT: staging or prod (chart ConfigMap).
 * - SENTRY_RELEASE: the commit the image was built from (Dockerfile build arg), so an error
 *   points to the code that ran even after the image is promoted to prod under another tag.
 * - SENTRY_TRACES_SAMPLE_RATE: share of requests traced, 0 to 1 (default 0: errors only).
 */
export function initSentry(env: NodeJS.ProcessEnv = process.env): boolean {
  const dsn = env.SENTRY_DSN;
  if (!dsn) return false;
  const rate = Number(env.SENTRY_TRACES_SAMPLE_RATE ?? "0");
  Sentry.init({
    dsn,
    environment: env.SENTRY_ENVIRONMENT || "development",
    release: env.SENTRY_RELEASE || undefined,
    tracesSampleRate: Number.isFinite(rate) && rate >= 0 && rate <= 1 ? rate : 0,
    // Probes and scrapes are not user traffic.
    ignoreTransactions: [/\/(healthz|readyz|metrics)$/],
    // Bodies hold passwords (login, registro) and tokens: never sent. No cookies, no user fields,
    // and no Authorization header; the rest of the request headers help to debug.
    dataCollection: {
      userInfo: false,
      cookies: false,
      httpBodies: [],
      httpHeaders: { request: { deny: ["authorization", "cookie"] }, response: false },
    },
  });
  return true;
}

initSentry();
