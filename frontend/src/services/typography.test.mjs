import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyTypographyRules } from './typography.ts';

test('typography autofix converges after the first pass', () => {
  const content = 'Текст - описание. И.И. Иванов на тесте за 2026 г. Wi-Fi.';
  const once = applyTypographyRules(content);

  assert.equal(applyTypographyRules(once), once);
});

test('typography converts numeric and time ranges but protects standards and minus signs', () => {
  const content = 'Диапазоны 3-5 и 10:00-11:00. ГОСТ 7.32-2017, СТО 1-2, ОСТ 1-2, Р 1-2. Значение −5−3.';

  assert.equal(
    applyTypographyRules(content),
    'Диапазоны 3–5 и\u00a010:00–11:00. ГОСТ 7.32-2017, СТО 1-2, ОСТ 1-2, Р 1-2. Значение −5−3.',
  );
});

test('typography preserves protected URLs, paths, and version-like tokens', () => {
  const content = 'URL https://example.org/file-3-5.txt, путь /tmp/file-10-20.txt, ссылка (images/file-10-20.txt), версия v1.2.3-4.';

  assert.equal(applyTypographyRules(content), content);
});
