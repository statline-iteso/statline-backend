import { EventEmitter } from "events";
import { request as httpsRequest } from "https";
import { crearClienteEnCluster } from "../src/lib/k8s";

jest.mock("https", () => ({ request: jest.fn() }));
const mockedRequest = httpsRequest as unknown as jest.Mock;

const files: Record<string, string> = {
  "/sa/ca.crt": "CA-PEM",
  "/sa/namespace": "statline-dev\n",
  "/sa/token": "tok-1\n",
};
const readFile = (p: string) => {
  const v = files[p];
  if (v === undefined) throw new Error(`missing ${p}`);
  return v;
};
const env = { KUBERNETES_SERVICE_HOST: "10.0.0.1", KUBERNETES_SERVICE_PORT: "443" };

/** Fake response: emits the body on the next tick once the request is ended. */
function fakeResponse(status: number, text: string) {
  const req = Object.assign(new EventEmitter(), {
    write: jest.fn(),
    end: jest.fn(() => {
      const res = Object.assign(new EventEmitter(), { statusCode: status });
      setImmediate(() => {
        callback?.(res);
        res.emit("data", Buffer.from(text));
        res.emit("end");
      });
    }),
    destroy: jest.fn(),
  });
  let callback: ((res: unknown) => void) | undefined;
  return { req, setCallback: (cb: (res: unknown) => void) => (callback = cb) };
}

describe("crearClienteEnCluster", () => {
  beforeEach(() => mockedRequest.mockReset());

  it("reads the namespace and CA once and sends the bearer token per call", async () => {
    const { http, namespace } = crearClienteEnCluster({ env, dir: "/sa", readFile });
    expect(namespace).toBe("statline-dev");

    const fake = fakeResponse(200, '{"ok":true}');
    mockedRequest.mockImplementation((_opts, cb) => {
      fake.setCallback(cb);
      return fake.req;
    });

    const res = await http({ method: "POST", path: "/apis/x", body: { a: 1 } });

    expect(res).toEqual({ status: 200, body: { ok: true } });
    const opts = mockedRequest.mock.calls[0]?.[0];
    expect(opts).toMatchObject({
      host: "10.0.0.1",
      port: 443,
      method: "POST",
      path: "/apis/x",
      ca: "CA-PEM",
      headers: expect.objectContaining({
        Authorization: "Bearer tok-1",
        "Content-Type": "application/json",
      }),
    });
    expect(fake.req.write).toHaveBeenCalledWith('{"a":1}');
  });

  it("returns non-JSON bodies as text and GETs without a body", async () => {
    const fake = fakeResponse(404, "not json");
    mockedRequest.mockImplementation((_opts, cb) => {
      fake.setCallback(cb);
      return fake.req;
    });
    const { http } = crearClienteEnCluster({ env, dir: "/sa", readFile });
    await expect(http({ method: "GET", path: "/apis/y" })).resolves.toEqual({
      status: 404,
      body: "not json",
    });
    expect(fake.req.write).not.toHaveBeenCalled();
  });

  it("returns undefined body for an empty response", async () => {
    const fake = fakeResponse(204, "");
    mockedRequest.mockImplementation((_opts, cb) => {
      fake.setCallback(cb);
      return fake.req;
    });
    const { http } = crearClienteEnCluster({ env, dir: "/sa", readFile });
    await expect(http({ method: "GET", path: "/apis/z" })).resolves.toEqual({
      status: 204,
      body: undefined,
    });
  });

  it("rejects on transport errors", async () => {
    const req = new EventEmitter() as EventEmitter & {
      write: jest.Mock;
      end: jest.Mock;
      destroy: jest.Mock;
    };
    req.write = jest.fn();
    req.destroy = jest.fn();
    req.end = jest.fn(() => req.emit("error", new Error("ECONNRESET")));
    mockedRequest.mockReturnValue(req);
    const { http } = crearClienteEnCluster({ env, dir: "/sa", readFile });
    await expect(http({ method: "GET", path: "/apis/q" })).rejects.toThrow("ECONNRESET");
  });

  it("destroys the request on timeout", () => {
    const req = Object.assign(new EventEmitter(), {
      write: jest.fn(),
      end: jest.fn(),
      destroy: jest.fn(),
    });
    mockedRequest.mockReturnValue(req);
    const { http } = crearClienteEnCluster({ env, dir: "/sa", readFile });
    void http({ method: "GET", path: "/apis/t" });
    req.emit("timeout");
    expect(req.destroy).toHaveBeenCalledWith(expect.any(Error));
  });

  it("fails fast without the in-cluster environment or namespace", () => {
    expect(() => crearClienteEnCluster({ env: {}, dir: "/sa", readFile })).toThrow();
    expect(() =>
      crearClienteEnCluster({
        env,
        dir: "/sa",
        readFile: (p) => (p.endsWith("namespace") ? "  \n" : readFile(p)),
      }),
    ).toThrow("sin namespace");
  });
});
