/**
 * One renderer for what a model writes (plan 11, E1 to E4): `<Markdown text={answer} />` on every chat surface. React
 * elements only (react-markdown with remark-gfm): raw HTML in the text is shown as text, never run; only http, https,
 * mailto and in-app `#/…` links are kept; images are not loaded, their alt text links to the source. What the person
 * typed stays plain text. Styles: markdown.css.
 *
 * `streaming` is set while the answer is still arriving: its unfinished tail is held back (settle). The component is
 * memoised on its props, so a long thread does not re-parse old answers when the person types, and a boundary falls back
 * to the plain text if the renderer ever throws.
 */
import { Component, memo, useEffect, useRef, useState, type ComponentProps, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { isExternal, safeHref, settle } from './markdownText';
import './markdown.css';

// "~5 days to ~8" is not strikethrough: only ~~two tildes~~ are
const PLUGINS: [typeof remarkGfm, { singleTilde: boolean }][] = [[remarkGfm, { singleTilde: false }]];

const urlTransform = (url: string): string => safeHref(url) ?? '';

/** The text of a node tree (what Copy puts on the clipboard). */
function textOf(n: ReactNode): string {
  if (n == null || typeof n === 'boolean') return '';
  if (typeof n === 'string' || typeof n === 'number') return String(n);
  if (Array.isArray(n)) return n.map(textOf).join('');
  if (typeof n === 'object' && 'props' in n) return textOf((n.props as { children?: ReactNode }).children);
  return '';
}

function Link({ href, children }: ComponentProps<'a'>) {
  const ok = safeHref(href);
  if (!ok) return <>{children}</>;
  return isExternal(ok) ? (
    <a href={ok} target="_blank" rel="noopener noreferrer">{children}</a>
  ) : (
    <a href={ok}>{children}</a>
  );
}

/** Images are never loaded: the alt text, as a link to the source when the source is allowed. */
function Image({ src, alt }: ComponentProps<'img'>) {
  const label = alt || 'image';
  const ok = typeof src === 'string' ? safeHref(src) : null;
  return ok ? <Link href={ok}>{label}</Link> : <>{label}</>;
}

function CodeBlock({ children }: ComponentProps<'pre'>) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number>(0);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const code = children && typeof children === 'object' && 'props' in children ? (children.props as { className?: string }) : {};
  const lang = /language-([\w+-]+)/.exec(code.className ?? '')?.[1];
  const copy = () => {
    const done = () => {
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 1600);
    };
    // no clipboard (an insecure origin): the label stays as it is
    if (navigator.clipboard) void navigator.clipboard.writeText(textOf(children).replace(/\n$/, '')).then(done, () => undefined);
  };
  return (
    <div className="md-pre">
      <div className="md-pre-bar">
        <span className="md-lang">{lang ?? ''}</span>
        <button type="button" className="md-copy" onClick={copy}>{copied ? 'Copied' : 'Copy'}</button>
        <span className="sr" aria-live="polite" role="status">{copied ? 'Copied to the clipboard' : ''}</span>
      </div>
      {/* a scrollable region is focusable so a keyboard can scroll it (WCAG 2.1.1) */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <pre tabIndex={0} aria-label={lang ? lang + ' code' : 'Code'}>{children}</pre>
    </div>
  );
}

/** Headings of an answer stay small: never an h1 or h2 in the page's outline. */
const heading = (tag: 'h3' | 'h4' | 'h5'): Components['h1'] => function Heading({ children }) {
  const T = tag;
  return <T className="md-h">{children}</T>;
};

const COMPONENTS: Components = {
  h1: heading('h3'), h2: heading('h3'), h3: heading('h4'), h4: heading('h5'), h5: heading('h5'), h6: heading('h5'),
  a: Link,
  img: Image,
  pre: CodeBlock,
  table: ({ children }) => (
    // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
    <div className="md-table" role="region" aria-label="Table" tabIndex={0}><table>{children}</table></div>
  ),
  input: ({ type, checked }) =>
    type === 'checkbox' ? <input type="checkbox" checked={!!checked} disabled readOnly aria-label={checked ? 'Done' : 'Not done'} /> : null,
};

interface BoundaryState { error: boolean; seen: string }

/** The plain text when the renderer throws; a new text gets a new try. */
class Boundary extends Component<{ text: string; children: ReactNode }, BoundaryState> {
  override state: BoundaryState = { error: false, seen: this.props.text };

  static getDerivedStateFromError(): Partial<BoundaryState> {
    return { error: true };
  }

  static getDerivedStateFromProps(props: { text: string }, state: BoundaryState): Partial<BoundaryState> | null {
    return props.text !== state.seen ? { error: false, seen: props.text } : null;
  }

  override render() {
    return this.state.error ? <p className="md-plain">{this.props.text}</p> : this.props.children;
  }
}

export interface MarkdownProps {
  text: string;
  /** the text is still arriving: hold back its unfinished tail */
  streaming?: boolean;
}

function MarkdownView({ text, streaming }: MarkdownProps) {
  const shown = streaming ? settle(text) : text;
  return (
    <div className="md">
      <Boundary text={text}>
        <ReactMarkdown remarkPlugins={PLUGINS} components={COMPONENTS} urlTransform={urlTransform}>{shown}</ReactMarkdown>
      </Boundary>
    </div>
  );
}

export const Markdown = memo(MarkdownView);
