import assert from 'node:assert/strict';
import { test } from 'node:test';
import { parseReportInline } from './markdown.ts';
import { createPreviewParagraph, estimateTableHeight, paginatePreviewBlocks, splitPreviewTableRow } from './previewPagination.ts';

const paragraph = text => ({ id: 'paragraph', type: 'p', data: { text }, estHeight: Math.ceil(text.length / 68) * 21 });
const textOf = block => (block.data.parts || parseReportInline(block.data.text)).map(part => part.text).join('');
const pageHeight = page => page.reduce((sum, block) => sum + block.estHeight, 0);

test('table height includes wrapping in the tallest cell, the header and caption', () => {
  const rows = ['| Параметр | Описание | Значение |', `| 1 | ${'Длинное описание параметра '.repeat(6)} | 2 |`];
  assert.ok(estimateTableHeight(rows, 'Таблица 1 — Параметры') >= 32 + 33 + 9 * 21 + 12);
  assert.ok(estimateTableHeight(rows, 'Название '.repeat(20)) > estimateTableHeight(rows, 'Название'));
  assert.ok(estimateTableHeight(rows, 'Название', true) < estimateTableHeight(rows, 'Название'));
});

test('text after a tall table fills remaining lines and continues without another indent', () => {
  const table = { id: 'table', type: 'table', data: {}, estHeight: 600 };
  const source = paragraph('Исследованы параметры устройства и полученные результаты. '.repeat(12));
  const pages = paginatePreviewBlocks([table, source]);
  assert.equal(pages[0][1]?.type, 'p');
  assert.ok(pages[0][1].estHeight <= 90);
  assert.equal(pages[0][1].data.continuation, false);
  assert.equal(pages[1][0].data.continuation, true);
  assert.equal(pages.flat().filter(block => block.type === 'p').map(textOf).join(''), textOf(source));
  assert.ok(pages.every(page => pageHeight(page) <= 690));
});

test('paragraphs longer than a page retain inline formatting, literals and whole formulas', () => {
  const source = paragraph(`**${'Проверено значение параметра '.repeat(150).trimEnd()}** и \`literal ** value\` $x_{a_b}$`);
  const pages = paginatePreviewBlocks([source]);
  assert.ok(pages.length > 2);
  assert.ok(pages.every(page => pageHeight(page) <= 690));
  assert.equal(pages.flat().map(textOf).join(''), textOf(source));
  assert.ok(pages[1][0].data.parts.some(part => part.bold));
  const parts = pages.flat().flatMap(block => block.data.parts);
  assert.equal(parts.filter(part => part.kind === 'math').length, 1);
  assert.ok(parts.some(part => part.kind === 'code' && part.text.includes('literal')));
});

test('a full page moves a paragraph before the safety margin rather than clipping a line', () => {
  const pages = paginatePreviewBlocks([{ id: 'filler', type: 'code', data: {}, estHeight: 675 }, paragraph('Короткий текст')]);
  assert.equal(pages.length, 2);
  assert.equal(pages[0].length, 1);
});

test('headings stay with following text and explicit H1, image and bibliography breaks survive', () => {
  const heading = { id: 'heading', type: 'h2', data: { title: 'Раздел' }, estHeight: 38 };
  const source = paragraph('Полученные результаты '.repeat(8));
  const pages = paginatePreviewBlocks([{ id: 'filler', type: 'code', data: {}, estHeight: 620 }, heading, source]);
  assert.equal(pages[1][0], heading);
  assert.equal(pages[1][1].type, 'p');
  for (const block of [
    { ...heading, type: 'h1' },
    { id: 'image', type: 'image', data: { layout: { page_break_before: true } }, estHeight: 100 },
    { id: 'bibliography', type: 'bibhead', data: {}, estHeight: 34 },
  ]) {
    assert.equal(paginatePreviewBlocks([paragraph('Текст'), block, source], true)[1][0], block);
  }
});

test('list fragments preserve item order and starting numbers', () => {
  const items = Array.from({ length: 5 }, (_, index) => ({ text: `${index + 4}. Пункт`, depth: 0, estHeight: 210 }));
  const pages = paginatePreviewBlocks([{ id: 'list', type: 'list', data: { items, start: 4 }, estHeight: 1050 }]);
  assert.deepEqual(pages.map(page => page[0].data.start), [4, 7]);
  assert.deepEqual(pages.flat().flatMap(block => block.data.items), items);
  assert.deepEqual(paginatePreviewBlocks([]), []);
});

test('cell parsing uses the same widths for optional final pipes, empty cells and escaped pipes', () => {
  assert.deepEqual(splitPreviewTableRow(String.raw`| A | B\|C | |`), ['A', 'B|C', '']);
  assert.deepEqual(splitPreviewTableRow('| A | B'), ['A', 'B']);
  assert.equal(estimateTableHeight(['| A | B |'], 'Title'), estimateTableHeight(['| A | B'], 'Title'));
  assert.ok(estimateTableHeight([`| ${'Длинный заголовок '.repeat(10)} | B |`], 'Title') > 150);
});

test('paragraph estimates account for word wrapping and the initial indent', () => {
  const text = ('параметр '.repeat(40)).trim();
  const data = createPreviewParagraph(text);
  assert.equal(data.linesEst, data.lines.length);
  assert.ok(data.linesEst >= Math.ceil(text.length / 58));
  assert.ok(data.lines[0].map(part => part.text).join('').trimEnd().length <= 53);
  assert.ok(data.lines.every(line => line.map(part => part.text).join('').trimEnd().length <= 58));
  assert.equal(createPreviewParagraph('`literal`').noIndent, true);
});

test('an unbroken technical literal can span pages without text loss', () => {
  const source = paragraph(`\`${'abc123'.repeat(500)}\``);
  const pages = paginatePreviewBlocks([source]);
  assert.ok(pages.length > 1);
  assert.equal(pages.flat().map(textOf).join(''), textOf(source));
  assert.ok(pages.every(page => pageHeight(page) <= 690));
  assert.ok(pages.flat().every(block => block.data.parts.every(part => part.kind === 'code')));
});

test('a formula near a page split remains one intact inline part', () => {
  const source = paragraph(`${'Результат '.repeat(190)}$x_{a_b} + \\frac{1}{2}$ конец`);
  const pages = paginatePreviewBlocks([{ id: 'table', type: 'table', data: {}, estHeight: 600 }, source]);
  const formulas = pages.flat().filter(block => block.type === 'p').flatMap(block => block.data.parts).filter(part => part.kind === 'math');
  assert.deepEqual(formulas.map(part => part.text), [String.raw`x_{a_b} + \frac{1}{2}`]);
  assert.equal(pages.flat().filter(block => block.type === 'p').map(textOf).join(''), textOf(source));
});
