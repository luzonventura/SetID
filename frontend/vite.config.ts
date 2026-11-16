/// <reference types="vitest/config" />
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

// La CSP solo se aplica al build: el servidor de desarrollo de Vite necesita scripts
// inline y WebSocket para la recarga en caliente.
const CSP = [
  "default-src 'self'",
  "script-src 'self'",
  "style-src 'self'",
  "font-src 'self'",
  // Carátulas: solo la CDN de Apple (Shazam, Apple Music e iTunes las sirven desde ahí).
  "img-src 'self' data: https://*.mzstatic.com",
  "connect-src 'self'",
  "object-src 'none'",
  "base-uri 'none'",
  "form-action 'none'",
  "frame-src 'none'",
].join('; ')

function contentSecurityPolicy(): Plugin {
  return {
    name: 'setid-csp',
    apply: 'build',
    transformIndexHtml(html) {
      return html.replace(
        '<meta charset="UTF-8" />',
        `<meta charset="UTF-8" />\n    <meta http-equiv="Content-Security-Policy" content="${CSP}" />`,
      )
    },
  }
}

export default defineConfig({
  // Rutas relativas: el build lo sirve el servidor local de pywebview.
  base: './',
  plugins: [react(), tailwindcss(), contentSecurityPolicy()],
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    // El tocadiscos 3D (three + R3F) va en su propio chunk de ~1 MB, cargado bajo demanda y
    // desde disco local: en una app de escritorio no penaliza.
    chunkSizeWarningLimit: 1200,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
