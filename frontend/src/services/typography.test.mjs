import assert from 'node:assert/strict';
import { test } from 'node:test';
import { applyTypographyRules } from './typography.ts';

test('typography autofix converges after the first pass', () => {
  const content = 'Текст - описание. И.И. Иванов на тесте за 2026 г. Wi-Fi.';
  const once = applyTypographyRules(content);

  assert.equal(applyTypographyRules(once), once);
});
