const escapeTableCell = (value: unknown): string => String(value ?? '')
  .replace(/\r?\n|\r/g, ' ')
  .replace(/\\/g, '\\\\')
  .replace(/\|/g, '\\|')
  .replace(/\s+/g, ' ')
  .trim();

export const buildMarkdownTable = (
  caption: string,
  headers: readonly (string | undefined)[],
  rows: readonly (readonly (string | undefined)[])[],
  columnCount = 3,
): string => {
  const count = Math.max(1, columnCount);
  const cleanCaption = (caption || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/^таблица\s*\d*\s*[:–—.-]?\s*/i, '')
    .trim() || 'Исходные данные';
  const headerCells = Array.from({ length: count }, (_, index) =>
    escapeTableCell(headers[index]) || 'Колонка'
  );
  const separator = Array.from({ length: count }, () => ':---');
  const lines = [
    `Таблица 1 — ${cleanCaption}`,
    '',
    `| ${headerCells.join(' | ')} |`,
    `| ${separator.join(' | ')} |`,
  ];

  for (const row of rows) {
    const cells = Array.from({ length: count }, (_, index) => escapeTableCell(row[index]));
    lines.push(`| ${cells.join(' | ')} |`);
  }

  return `\n${lines.join('\n')}\n\n`;
};
