import * as Sentry from "@sentry/node";
import type { ErrorRequestHandler, RequestHandler } from "express";
import { Prisma } from "@prisma/client";
import { ZodError } from "zod";
import { AppError } from "../lib/errors";

export const notFoundHandler: RequestHandler = (_req, res) => {
  res.status(404).json({ error: { code: "NOT_FOUND", message: "Ruta no encontrada" } });
};

export const errorHandler: ErrorRequestHandler = (err, req, res, _next) => {
  if (err instanceof AppError) {
    res
      .status(err.status)
      .json({ error: { code: err.code, message: err.message, details: err.details } });
    return;
  }
  if (err instanceof ZodError) {
    res.status(400).json({
      error: {
        code: "VALIDATION_ERROR",
        message: "Solicitud inválida",
        details: err.issues.map((i) => ({ path: i.path.join("."), message: i.message })),
      },
    });
    return;
  }
  if (typeof err === "object" && err !== null && "type" in err && err.type === "entity.too.large") {
    res
      .status(413)
      .json({ error: { code: "PAYLOAD_TOO_LARGE", message: "Cuerpo demasiado grande" } });
    return;
  }
  if (err instanceof Prisma.PrismaClientKnownRequestError) {
    if (err.code === "P2025") {
      res.status(404).json({ error: { code: "NOT_FOUND", message: "Recurso no encontrado" } });
      return;
    }
    if (err.code === "P2002") {
      res.status(409).json({ error: { code: "DUPLICATE", message: "El recurso ya existe" } });
      return;
    }
    if (err.code === "P2003") {
      res.status(400).json({
        error: { code: "INVALID_REFERENCE", message: "Referencia a un recurso inexistente" },
      });
      return;
    }
  }
  // Only what ends as a 500 goes to Sentry: the cases above are client errors, not bugs.
  // A no-op when Sentry is off (no SENTRY_DSN).
  Sentry.captureException(err);
  req.log?.error({ err }, "unhandled error");
  res.status(500).json({ error: { code: "INTERNAL", message: "Error interno" } });
};
