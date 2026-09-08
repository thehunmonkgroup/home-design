import { defineConfig } from 'vite';

export default defineConfig({
  base: './',
  publicDir: false,
  build: { rollupOptions: { input: 'capture.html' } },
});
