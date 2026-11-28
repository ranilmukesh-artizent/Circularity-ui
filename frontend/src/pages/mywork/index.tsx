// Loaders, not components: src/pages/registry.tsx wraps each in React.lazy, so every page is its own chunk.
// 28 Nov 2026: My work and My Tasks are one page (pages/home/TasksPage); #/mywork still opens it.
export const pages = {
  mywork: () => import('../home/TasksPage').then((m) => m.TasksPage),
};
