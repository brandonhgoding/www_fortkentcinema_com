import { defineConfig } from 'vite';
import { resolve } from 'node:path';

export default defineConfig({
  build: {
    outDir: resolve(import.meta.dirname, '../static/js'),
    emptyOutDir: false,
    lib: {
      entry: resolve(import.meta.dirname, 'effects/main.js'),
      formats: ['es'],
      fileName: () => 'effects.js',
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./vitest.setup.js'],
    globals: true,
  },
});
