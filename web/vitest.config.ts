import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    environment: 'node',
    include: ['app/**/*.test.{ts,tsx}', 'config/**/*.test.ts', 'tests/**/*.test.ts'],
    exclude: ['node_modules', '.next', '.vinext', 'dist'],
    fileParallelism: false,
    pool: 'forks',
  },
});
