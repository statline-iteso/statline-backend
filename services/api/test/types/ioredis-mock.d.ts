// ioredis-mock ships without type declarations; it mirrors the ioredis Redis class.
declare module "ioredis-mock" {
  import type Redis from "ioredis";
  const RedisMock: new (...args: unknown[]) => Redis;
  export default RedisMock;
}
