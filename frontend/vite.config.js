import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Refactor Fase design/architettura: frontend a componenti React con routing a pagine.
export default defineConfig({
  plugins: [react()],
});
