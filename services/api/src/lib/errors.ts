export class AppError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message: string,
    public readonly details?: unknown,
  ) {
    super(message);
  }
}

export const notFound = (what = "Recurso") =>
  new AppError("NOT_FOUND", 404, `${what} no encontrado`);
export const unauthorized = (message = "Token ausente o inválido") =>
  new AppError("UNAUTHORIZED", 401, message);
export const badRequest = (message: string) => new AppError("BAD_REQUEST", 400, message);
export const forbidden = () => new AppError("FORBIDDEN", 403, "Permisos insuficientes");
