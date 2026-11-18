import { Router, type RequestHandler } from "express";
import { z, type ZodTypeAny } from "zod";
import { ah } from "./async";
import { notFound } from "./errors";
import type { CatalogCache } from "./cache";

/* eslint-disable @typescript-eslint/no-explicit-any -- Prisma delegates have per-model generic
   signatures; this factory only forwards validated args, so a structural type is enough. */
export interface CrudDelegate {
  findMany(args: any): Promise<unknown[]>;
  count(args: any): Promise<number>;
  findUnique(args: any): Promise<unknown | null>;
  create(args: any): Promise<unknown>;
  update(args: any): Promise<unknown>;
  delete(args: any): Promise<unknown>;
}
/* eslint-enable @typescript-eslint/no-explicit-any */

export const IdParamSchema = z.object({ id: z.string().uuid() });

export const PaginationSchema = z.object({
  page: z.coerce.number().int().min(1).default(1),
  pageSize: z.coerce.number().int().min(1).max(100).default(20),
});

export interface CrudOptions<Q extends ZodTypeAny> {
  /** Singular resource name for error messages, e.g. "Liga". */
  name: string;
  delegate: CrudDelegate;
  createSchema: ZodTypeAny;
  updateSchema: ZodTypeAny;
  /** Filters accepted on GET {base} (proposal §2.2). */
  filterSchema: Q;
  where: (filters: z.infer<Q>) => Record<string, unknown>;
  orderBy?: Record<string, "asc" | "desc">;
  include?: Record<string, unknown>;
  /** Middleware applied to POST, PUT and DELETE (e.g. requireRole("ADMIN")). */
  writeGuard?: RequestHandler;
  /** Omit standard operations (e.g. EjecucionIngesta only exposes GET and DELETE). */
  only?: Array<"list" | "get" | "create" | "update" | "delete">;
  /** Catalog cache: reads of list/get are cached, successful writes invalidate. */
  cache?: CatalogCache;
}

/**
 * Standard operations for a component: POST {base}, GET {base}, GET {base}/:id,
 * PUT {base}/:id and DELETE {base}/:id. Extra methods are added by each router.
 */
export function createCrudRouter<Q extends ZodTypeAny>(opts: CrudOptions<Q>): Router {
  const router = Router();
  const enabled = new Set(opts.only ?? ["list", "get", "create", "update", "delete"]);
  const guard: RequestHandler = opts.writeGuard ?? ((_req, _res, next) => next());
  const read: RequestHandler[] = opts.cache ? [opts.cache.read] : [];
  const write: RequestHandler[] = opts.cache ? [opts.cache.invalidate] : [];

  if (enabled.has("list")) {
    router.get(
      "/",
      ...read,
      ah(async (req, res) => {
        const { page, pageSize } = PaginationSchema.parse(req.query);
        const where = opts.where(opts.filterSchema.parse(req.query));
        const [data, total] = await Promise.all([
          opts.delegate.findMany({
            where,
            include: opts.include,
            orderBy: opts.orderBy,
            skip: (page - 1) * pageSize,
            take: pageSize,
          }),
          opts.delegate.count({ where }),
        ]);
        res.json({ data, total, page, pageSize });
      }),
    );
  }

  if (enabled.has("get")) {
    router.get(
      "/:id",
      ...read,
      ah(async (req, res) => {
        const { id } = IdParamSchema.parse(req.params);
        const item = await opts.delegate.findUnique({ where: { id }, include: opts.include });
        if (!item) throw notFound(opts.name);
        res.json(item);
      }),
    );
  }

  if (enabled.has("create")) {
    router.post(
      "/",
      guard,
      ...write,
      ah(async (req, res) => {
        const data = opts.createSchema.parse(req.body);
        res.status(201).json(await opts.delegate.create({ data }));
      }),
    );
  }

  if (enabled.has("update")) {
    router.put(
      "/:id",
      guard,
      ...write,
      ah(async (req, res) => {
        const { id } = IdParamSchema.parse(req.params);
        const data = opts.updateSchema.parse(req.body);
        res.json(await opts.delegate.update({ where: { id }, data }));
      }),
    );
  }

  if (enabled.has("delete")) {
    router.delete(
      "/:id",
      guard,
      ...write,
      ah(async (req, res) => {
        const { id } = IdParamSchema.parse(req.params);
        await opts.delegate.delete({ where: { id } });
        res.status(204).end();
      }),
    );
  }

  return router;
}
