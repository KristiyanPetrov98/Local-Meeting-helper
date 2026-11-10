import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import path from 'node:path';
export default defineConfig({
  root: path.resolve('apps/web'), base: '/', plugins: [react(), tailwindcss()],
  build: { outDir: 'dist', emptyOutDir: true }
});
