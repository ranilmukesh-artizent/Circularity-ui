// @vitest-environment node
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const css = readFileSync(new URL('./assistant.css', import.meta.url), 'utf8');
const canvas = readFileSync(new URL('../pages/modeler/canvas.css', import.meta.url), 'utf8');
const strip = (c: string) => c.replace(/\/\*[\s\S]*?\*\//g, '');
/** The declarations inside the first block whose selector is exactly `sel`. */
const block = (c: string, sel: string): string => {
  const m = new RegExp('(?:^|\\})\\s*' + sel.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\s*\\{([^}]*)\\}').exec(strip(c));
  return m ? m[1] : '';
};

describe('plan 10 tokens (assistant.css)', () => {
  it('defines the revision, hold and block tokens for light and dark', () => {
    const light = block(css, ':root');
    const dark = block(css, ':root[data-theme="dark"]');
    for (const t of ['--as-rev', '--as-rev-bg', '--as-hold', '--as-block']) {
      expect(light, t + ' light').toContain(t + ':');
      expect(dark, t + ' dark').toContain(t + ':');
    }
    expect(light).toContain('--as-rev-bg: rgba(20, 20, 20, .035)');
    expect(dark).toContain('--as-rev-bg: rgba(243, 242, 238, .05)');
  });

  it('defines the spacing, motion and Modeler layout tokens', () => {
    const light = block(css, ':root');
    for (const t of ['--as-pad: 16px', '--as-gap: 20px', '--as-radius: 8px', '--as-dur: 240ms', '--as-ease: cubic-bezier(.2, 0, 0, 1)',
      '--mdl-agent-w: 384px', '--mdl-agent-w-sm: 320px', '--mdl-rail-w: 340px', '--mdl-strip-w: 44px', '--mdl-bar-h: 48px', '--mdl-head: 168px', '--mdl-grid: 24px']) {
      expect(light, t).toContain(t);
    }
  });

  it('keys the dark values off data-theme, not prefers-color-scheme', () => {
    expect(strip(css)).not.toContain('prefers-color-scheme');
  });

  it('never uses transition: all, and the node motion animates only stroke-dashoffset and opacity', () => {
    expect(strip(css) + strip(canvas)).not.toMatch(/transition:\s*all/);
    const kf = [...strip(canvas).matchAll(/@keyframes[^{]+\{((?:[^{}]*\{[^}]*\})+)\s*\}/g)].map((m) => m[1]).join(' ');
    const props = new Set([...kf.matchAll(/([a-z-]+)\s*:/g)].map((m) => m[1]));
    expect([...props].sort()).toEqual(['opacity', 'stroke-dashoffset']);
  });

  it('plays the apply motion not at all under reduced motion', () => {
    expect(canvas).toMatch(/@media \(prefers-reduced-motion: reduce\)[\s\S]*rev-done[\s\S]*display: none/);
  });

  it('scopes the node look to the Modeler canvas, never the shared graph', () => {
    const rules = strip(canvas).split('}').map((r) => r.split('{')[0].trim()).filter((s) => s && !s.startsWith('@') && !/^(from|to|\d+%)/.test(s));
    for (const sel of rules) for (const part of sel.split(',')) expect(part.trim(), part).toMatch(/\.mdl-(canvas|node)/);
  });
});
