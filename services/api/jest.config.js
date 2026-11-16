/** @type {import('jest').Config} */
module.exports = {
  preset: "ts-jest",
  testEnvironment: "node",
  roots: ["<rootDir>/test"],
  collectCoverageFrom: ["src/**/*.ts", "!src/server.ts"],
  // CI fails if coverage drops below 70 % (proposal §4.3).
  coverageThreshold: {
    global: { lines: 70, statements: 70, functions: 70, branches: 60 },
  },
};
