import { release } from 'node:os';
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// In Docker the API is reachable as http://api:8000; locally it is on localhost.
const apiTarget = process.env.API_PROXY_TARGET ?? 'http://localhost:8000';

// File watching by polling, for bind mounts that deliver no change events (a Windows drive under WSL, some VMs).
// DEV_POLLING=1 turns it on, DEV_POLLING=0 off; unset, it is on only under a WSL2 kernel, the same default as
// watchfiles, which the api's and source-sim's uvicorn --reload use (docker-compose.yml).
const devPolling = process.env.DEV_POLLING;
const usePolling =
  devPolling === undefined || devPolling === '' ? /microsoft-standard/i.test(release()) : devPolling === '1' || devPolling === 'true';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    watch: { usePolling },
    proxy: { '/api': apiTarget, '/mcp': apiTarget }, // /mcp: the MCP server (B16), used by the MCP playground
  },
  // Vite 8 minifies CSS with Lightning CSS, which rejects invalid rules instead of copying them through. The stylesheet
  // extracted from the static demo has `@container or (...)` (`or` is a reserved word, so browsers ignore those rules
  // too); recovering drops such rules with a build warning instead of failing the build.
  css: { lightningcss: { errorRecovery: true } },
  // Pages are lazy chunks (src/pages/registry.tsx). React and the router go into their own `vendor` chunk, which
  // changes less often than app code and so stays cached across deploys. (Vite 8: rolldownOptions replaces the
  // deprecated rollupOptions; output.codeSplitting.groups replaces manualChunks.)
  build: {
    rolldownOptions: {
      output: {
        codeSplitting: {
          groups: [{ name: 'vendor', test: /node_modules[\\/](react|react-dom|react-router|react-router-dom|scheduler|@remix-run[\\/]router)[\\/]/ }],
        },
      },
    },
  },
});
