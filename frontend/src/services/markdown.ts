import MarkdownIt from 'markdown-it';
import { applyTypographyRules } from './typography.ts';

export interface InlinePart {
  kind: 'text' | 'code' | 'math';
  text: string;
  bold: boolean;
  italic: boolean;
}

export interface MarkdownImageSource {
  alt: string;
  src: string;
}

const markdown = new MarkdownIt('commonmark', { html: false, typographer: false });

// Math is opaque to CommonMark: underscores and backslashes belong to LaTeX.
markdown.inline.ruler.before('escape', 'report_math', (state, silent) => {
  if (state.src[state.pos] !== '$') return false;
  const match = /^\$([^$\n]+)\$/.exec(state.src.slice(state.pos));
  if (!match) return false;
  if (!silent) {
    const token = state.push('report_math', '', 0);
    token.content = match[1];
  }
  state.pos += match[0].length;
  return true;
});

export function parseReportInline(source: string): InlinePart[] {
  const parts: InlinePart[] = [];
  let boldDepth = 0;
  let italicDepth = 0;
  const tokens = markdown.parseInline(source, {})[0]?.children || [];
  for (const token of tokens) {
    if (token.type === 'strong_open') boldDepth++;
    else if (token.type === 'strong_close') boldDepth--;
    else if (token.type === 'em_open') italicDepth++;
    else if (token.type === 'em_close') italicDepth--;
    else if (['text', 'code_inline', 'report_math', 'softbreak', 'hardbreak'].includes(token.type)) {
      const kind = token.type === 'code_inline' ? 'code' : token.type === 'report_math' ? 'math' : 'text';
      const text = token.type.endsWith('break') ? ' ' : token.content;
      parts.push({ kind, text: kind === 'text' ? applyTypographyRules(text) : text, bold: boldDepth > 0, italic: italicDepth > 0 });
    }
  }
  return parts;
}

export function extractMarkdownImageSources(source: string): MarkdownImageSource[] {
  const images: MarkdownImageSource[] = [];
  for (const token of markdown.parse(source, {})) {
    for (const child of token.children || []) {
      if (child.type !== 'image') continue;
      const src = child.attrGet('src');
      if (src) images.push({ alt: String(child.content), src: String(src) });
    }
  }
  return images;
}
