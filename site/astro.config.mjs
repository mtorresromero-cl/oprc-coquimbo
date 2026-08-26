// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  redirects: {
    '/parlamentarios': '/congreso/',
    '/consejo-regional': '/congreso/',
    '/dashboard': '/congreso/',
  },
  vite: {
    plugins: [tailwindcss()]
  }
});