import request from "supertest";
import { Router } from "express";
import * as Sentry from "@sentry/node";
import { AppError } from "../src/lib/errors";
import { initSentry } from "../src/instrument";
import { errorHandler } from "../src/middleware/error-handler";

jest.mock("@sentry/node", () => ({ init: jest.fn(), captureException: jest.fn() }));

const sentry = Sentry as jest.Mocked<typeof Sentry>;

describe("initSentry", () => {
  beforeEach(() => jest.clearAllMocks());

  it("stays off without SENTRY_DSN or with a placeholder", () => {
    expect(initSentry({})).toBe(false);
    expect(initSentry({ SENTRY_DSN: "set-me" })).toBe(false);
    expect(sentry.init).not.toHaveBeenCalled();
  });

  it("starts with the environment, the release and no request bodies", () => {
    expect(
      initSentry({
        SENTRY_DSN: "https://key@o1.ingest.sentry.io/1",
        SENTRY_ENVIRONMENT: "staging",
        SENTRY_RELEASE: "abc1234",
        SENTRY_TRACES_SAMPLE_RATE: "0.2",
      }),
    ).toBe(true);
    const opciones = sentry.init.mock.calls[0]?.[0];
    expect(opciones).toMatchObject({
      environment: "staging",
      release: "abc1234",
      tracesSampleRate: 0.2,
    });
    expect(opciones?.dataCollection).toMatchObject({
      httpBodies: [],
      cookies: false,
      userInfo: false,
    });
  });

  it("falls back to no tracing on an invalid sample rate", () => {
    initSentry({ SENTRY_DSN: "https://key@o1.ingest.sentry.io/1", SENTRY_TRACES_SAMPLE_RATE: "7" });
    expect(sentry.init.mock.calls[0]?.[0]).toMatchObject({
      tracesSampleRate: 0,
      environment: "development",
    });
  });
});

describe("errorHandler and Sentry", () => {
  const appCon = (err: unknown) => {
    const express = jest.requireActual<typeof import("express")>("express");
    const app = express();
    const router = Router();
    router.get("/x", () => {
      throw err;
    });
    app.use(router);
    app.use(errorHandler);
    return app;
  };

  beforeEach(() => jest.clearAllMocks());

  it("reports an unexpected error (500)", async () => {
    const err = new Error("boom");
    await request(appCon(err)).get("/x").expect(500);
    expect(sentry.captureException).toHaveBeenCalledWith(err);
  });

  it("does not report a client error", async () => {
    await request(appCon(new AppError("NOT_FOUND", 404, "no")))
      .get("/x")
      .expect(404);
    expect(sentry.captureException).not.toHaveBeenCalled();
  });
});
