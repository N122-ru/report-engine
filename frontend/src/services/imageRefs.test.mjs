import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { test } from 'node:test';
import { canonicalImageName, resolveImageName } from './imageRefs.ts';

const cases = JSON.parse(await readFile(new URL('../../../tests/image_ref_cases.json', import.meta.url), 'utf8'));

test('image reference matching follows the backend contract vectors', () => {
  for (const item of cases) {
    assert.equal(canonicalImageName(item.reference), item.canonical);
    assert.equal(resolveImageName(item.reference, item.names), item.match ?? undefined);
  }
});
