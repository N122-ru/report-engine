import assert from 'node:assert/strict';
import { test } from 'node:test';
import { buildMarkdownTable } from './tableMarkdown.ts';

test('table markdown escapes pipes and keeps cell content on one row', () => {
  const markdown = buildMarkdownTable(
    'Таблица 1: Сводка',
    ['Параметр | протокол', 'Значение', 'Примечание'],
    [['TCP | UDP', '443', 'TLS\nканал']],
  );

  assert.equal(markdown, [
    '',
    'Таблица 1 — Сводка',
    '',
    '| Параметр \\| протокол | Значение | Примечание |',
    '| :--- | :--- | :--- |',
    '| TCP \\| UDP | 443 | TLS канал |',
    '',
    '',
  ].join('\n'));
});

test('table markdown supplies stable fallback values for empty cells', () => {
  const markdown = buildMarkdownTable('', ['', '  ', 'Комментарий'], [['', undefined, '']]);

  assert.match(markdown, /Таблица 1 — Исходные данные/);
  assert.match(markdown, /\| Колонка \| Колонка \| Комментарий \|/);
  assert.match(markdown, /\|  \|  \|  \|/);
});
