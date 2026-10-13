import assert from 'node:assert/strict';
import { test } from 'node:test';
import { extractMarkdownImageSources, parseReportInline } from './markdown.ts';

const plainText = source => parseReportInline(source).map(part => part.text).join('');

test('literal asterisks, apostrophes, double quotes and backslash-n survive matching code delimiters', () => {
  const literal = 'print(`"value"`) ** * \'word\' \\n';
  assert.equal(plainText(`Текст \`\`${literal}\`\` конец`), `Текст ${literal} конец`);
  assert.equal(plainText(String.raw`Литералы \* и \*\*; O'Reilly`).replaceAll('\u00a0', ' '), "Литералы * и **; O'Reilly");
  assert.equal(plainText(String.raw`Строка\nпродолжение`), String.raw`Строка\nпродолжение`);
});

test('nested strong and emphasis use Markdown tokens while inline literals never become formatting', () => {
  const parts = parseReportInline('**Жирный *курсив* текст**; `**` и `*`');
  assert.ok(parts.some(part => part.text === 'курсив' && part.bold && part.italic));
  assert.ok(parts.some(part => part.text === ' текст' && part.bold && !part.italic));
  assert.ok(parts.some(part => part.text === '**' && part.kind === 'code'));
  assert.ok(parts.some(part => part.text === '*' && part.kind === 'code'));
});

test('unmatched backticks remain visible and formulas preserve their source', () => {
  assert.equal(plainText('Начало ``незакрыто'), 'Начало ``незакрыто');
  const latex = String.raw`x_{a_b} + \frac{1}{2}`;
  const parts = parseReportInline(`Формула $${latex}$ и \`$не формула$\``);
  assert.ok(parts.some(part => part.kind === 'math' && part.text === latex));
  assert.ok(parts.some(part => part.kind === 'code' && part.text === '$не формула$'));
});

test('ordinary prose uses typography but technical strings and HTML stay literal', () => {
  assert.equal(plainText('Проза "значение"; `"literal"`'), 'Проза «значение»; "literal"');
  assert.equal(plainText('<script>alert(1)</script>'), '<script>alert(1)</script>');
});

test('image extraction handles optional Markdown titles and ignores fenced code', () => {
  const images = extractMarkdownImageSources(
    '![Схема](screen.png "Скрин стенда")\n\n~~~text\n![Литерал](ignored.png)\n~~~\n',
  );
  assert.deepEqual(images, [{ alt: 'Схема', src: 'screen.png' }]);
});
