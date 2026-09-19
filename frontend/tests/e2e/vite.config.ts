/** Test-only entry point. Production vite.config.ts never loads these aliases. */
import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  optimizeDeps: { entries: ['tests/e2e/index.html'] },
  resolve: {
    alias: {
      '@clerk/react': fileURLToPath(new URL('./clerk-stub.tsx', import.meta.url)),
    },
  },
})
