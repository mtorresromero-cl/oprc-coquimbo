// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  redirects: {
    '/congreso': '/parlamentarios/',
    '/dashboard': '/parlamentarios/',
    '/parlamentarios/asesores': '/parlamentarios/gastos/#personal-apoyo',
  },
  vite: {
    plugins: [tailwindcss()]
  }
});