// Loaders, not components: src/pages/registry.tsx wraps each in React.lazy, so every page is its own chunk.
export const pages = {
  'agent-activity': () => import('./AgentActivityPage').then((m) => m.AgentActivityPage),
};
