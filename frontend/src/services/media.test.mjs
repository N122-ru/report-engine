import assert from 'node:assert/strict';
import { test } from 'node:test';
import { mergeImageFiles, sortMediaFiles } from './media.ts';

test('dropped images without a MIME type are accepted by extension and retain original bytes', async () => {
  const image = new File(['original bytes'], 'Снимок.PNG', { lastModified: 123 });
  const invalid = new File(['text'], 'notes.txt');
  const result = mergeImageFiles([], [image, invalid]);
  assert.equal(result.added.length, 1);
  assert.equal(result.added[0].type, 'image/png');
  assert.equal(result.added[0].name, image.name);
  assert.equal(result.added[0].lastModified, image.lastModified);
  assert.equal(await result.added[0].text(), 'original bytes');
  assert.deepEqual(result.rejected, ['notes.txt']);
});

test('adding a batch deduplicates both existing and newly added server-normalized names', () => {
  const original = new File(['first'], 'Снимок_1.png', { type: 'image/png' });
  const duplicate = new File(['other bytes'], 'Снимок 1.png', { type: 'image/png' });
  const next = new File(['next'], 'next.png', { type: 'image/png' });
  const result = mergeImageFiles([original], [duplicate, next, next]);
  assert.deepEqual(result.images, [original, next]);
  assert.deepEqual(result.added, [next]);
  assert.deepEqual(result.duplicates, ['Снимок 1.png', 'next.png']);
});

test('media input accepts only backend-supported image formats and size', () => {
  const supported = new File(['png'], 'screen.png', { type: 'image/png' });
  const unsupported = new File(['svg'], 'screen.svg', { type: 'image/svg+xml' });
  const oversized = new File(['x'], 'large.png', { type: 'image/png' });
  Object.defineProperty(oversized, 'size', { value: 15 * 1024 * 1024 + 1 });
  const result = mergeImageFiles([], [supported, unsupported, oversized]);
  assert.deepEqual(result.added, [supported]);
  assert.deepEqual(result.rejected, ['screen.svg', 'large.png']);
});

test('media sorting uses natural filenames, offers reverse and size order, and never mutates attachments', () => {
  const files = [
    new File(['123'], 'Снимок_10.png'),
    new File(['1'], 'Снимок_2.png'),
    new File(['12'], 'Снимок_1.png'),
  ];
  assert.deepEqual(sortMediaFiles(files, 'name-asc').map(file => file.name), ['Снимок_1.png', 'Снимок_2.png', 'Снимок_10.png']);
  assert.deepEqual(sortMediaFiles(files, 'name-desc').map(file => file.name), ['Снимок_10.png', 'Снимок_2.png', 'Снимок_1.png']);
  assert.deepEqual(sortMediaFiles(files, 'size-desc').map(file => file.size), [3, 2, 1]);
  assert.equal(files[0].name, 'Снимок_10.png');
});
