import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In Docker the API is reachable as http://api:8000; locally it is on localhost.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { '/api': apiTarget, '/mcp': apiTarget }, // /mcp: the MCP server (B16), used by the MCP playground
  },
  // Vite 8 minifies CSS with Lightning CSS, which rejects invalid rules instead of copying them through. The stylesheet
  // extracted from the static demo has `@container or (...)` (`or` is a reserved word, so browsers ignore those rules
  // too); recovering drops such rules with a build warning instead of failing the build.
  css: { lightningcss: { errorRecovery: true } },
});
