import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/postcss';
import { defineConfig } from 'vite';
export default defineConfig({
  base: './',
  publicDir: process.env.HOME_DESIGN_PUBLIC_DIR || 'public',
  css: { postcss: { plugins: [tailwindcss()] } },
  plugins: [react()],
  server: process.env.CODEX_SANDBOX === 'seatbelt'
    ? { watch: { useFsEvents: false, usePolling: true } }
    : undefined,
});
