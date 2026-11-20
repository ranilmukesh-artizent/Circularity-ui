// Loaders, not components: src/pages/registry.tsx wraps each in React.lazy, so every page is its own chunk.
export const pages = {
  home: () => import('./HomePage').then((m) => m.HomePage),
  tasks: () => import('./TasksPage').then((m) => m.TasksPage),
  alerts: () => import('./AlertsPage').then((m) => m.AlertsPage),
  reports: () => import('./ReportsPage').then((m) => m.ReportsPage),
  checks: () => import('./ChecksPage').then((m) => m.ChecksPage),
  settings: () => import('./SettingsPage').then((m) => m.SettingsPage),
};
