import pino from "pino";
import { createRedis, withTimeout } from "../src/lib/redis";

describe("redis client", () => {
  it("withTimeout rejects when the promise is too slow and resolves otherwise", async () => {
    await expect(withTimeout(new Promise(() => undefined), 10, "slow")).rejects.toThrow("slow");
    await expect(withTimeout(Promise.resolve(7), 1000)).resolves.toBe(7);
  });

  it("ping fails within the timeout when Redis is unreachable, and close() does not throw", async () => {
    const redis = createRedis("redis://127.0.0.1:1", pino({ level: "silent" }));
    await expect(redis.ping(300)).rejects.toThrow();
    await expect(redis.close()).resolves.toBeUndefined();
    await expect(redis.close()).resolves.toBeUndefined();
  });
});
