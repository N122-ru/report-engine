import { ReferenceItem } from '../types';
import { applyTypographyRules } from './typography';

/**
 * Mirror backend/app/engine/bibliography.py (GOST R 7.0.5-2008).
 * Keep format changes identical in both implementations.
 */

const clean = (v: unknown): string => (v === null || v === undefined ? '' : String(v).trim().replace(/\.+$/, ''));

export const normalizeKind = (v: unknown): string => {
  const kind = String(v ?? '').trim().toLowerCase();
  return ['book', 'article', 'website', 'standard'].includes(kind) ? kind : 'book';
};

const dot = (s: string): string => {
  const t = s.trim();
  return t.endsWith('.') ? t : t + '.';
};

const head = (authorsRaw: string, title: string): string => {
  const authors = (authorsRaw || '').trim();
  let h = '';
  if (authors) h = authors.endsWith('.') ? authors : authors + '.';
  if (title) h = h ? `${h} ${title}` : title;
  return h;
};

const join = (parts: string[]): string => {
  const chunks = parts.map(p => (p || '').trim()).filter(Boolean);
  if (chunks.length === 0) return 'Источник';
  let text = chunks[0];
  for (const chunk of chunks.slice(1)) text += ` – ${chunk}`;
  return text.replace(/\.{2,}/g, '.');
};

export function formatReference(ref: ReferenceItem): string {
  return applyTypographyRules(composeReference(ref));
}

function composeReference(ref: ReferenceItem): string {
  const kind = normalizeKind(ref.kind);
  const authors = (ref.authors || '').trim();
  const title = clean(ref.title);
  const place = (ref.place || '').trim();
  const publisher = clean(ref.publisher);
  const year = clean(ref.year);
  const details = clean(ref.details);
  const url = (ref.url || '').trim();

  if (kind === 'article') {
    let h = head(authors, title);
    if (publisher) h = h ? `${h} // ${publisher}` : publisher;
    const tail = [h ? dot(h) : '', ...[year, details].filter(Boolean).map(dot)].filter(Boolean);
    return join(tail);
  }

  if (kind === 'website') {
    if (!title && !url && !details) return 'Источник';
    const h = title || 'Электронный ресурс';
    let text = `${h} : [Электронный ресурс].`;
    if (url) {
      text += ` – URL: ${url}`;
      if (details) text += ` (дата обращения: ${details})`;
      text += '.';
    } else if (details) {
      text += ` – ${details}.`;
    }
    return text.replace(/\.{2,}/g, '.');
  }

  const h = head(authors, title);
  let pub = publisher;
  if (place && publisher) pub = `${place}: ${publisher}`;
  else if (place) pub = place;
  if (pub && year) pub = `${pub}, ${year}`;
  else if (year) pub = year;
  const chunks: string[] = [];
  if (h) chunks.push(dot(h));
  if (pub) chunks.push(dot(pub));
  if (details) chunks.push(dot(details));
  return join(chunks);
}
