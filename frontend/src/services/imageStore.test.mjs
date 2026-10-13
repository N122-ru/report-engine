import 'fake-indexeddb/auto';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { deleteStoredImage, deleteStoredImageByName, deleteStoredImageFile, getStoredImages, saveStoredImage } from './imageStore.ts';

test('stores original bytes and manifest across reads', async () => {
  const file = new File(['original bytes'], 'Схема сети.png', {
    type: 'image/png', lastModified: 12345,
  });
  await saveStoredImage(file);

  const stored = await getStoredImages();
  assert.equal(stored.length, 1);
  assert.equal(stored[0].filename, file.name);
  assert.equal(stored[0].size, file.size);
  assert.match(stored[0].sha256, /^[a-f0-9]{64}$/);
  assert.equal(await stored[0].file.text(), 'original bytes');
  assert.equal(stored[0].file.lastModified, 12345);
  await deleteStoredImage(file.name);
});

test('never replaces an original with different bytes under the same name', async () => {
  const original = new File(['original'], 'capture.png', { type: 'image/png' });
  await saveStoredImage(original);
  await saveStoredImage(new File(['original'], original.name, { type: original.type }));
  await assert.rejects(
    saveStoredImage(new File(['cropped'], original.name, { type: original.type })),
    /другими данными/,
  );
  const stored = await getStoredImages();
  assert.equal(await stored.find(item => item.filename === original.name).file.text(), 'original');
  await deleteStoredImage(original.name);
});

test('canonical server name is saved before retiring the browser filename', async () => {
  const original = new File(['bytes'], 'Схема сети.png', { type: 'image/png' });
  await saveStoredImage(original);
  await saveStoredImage(new File([original], 'Схема_сети.png', { type: original.type }));
  await deleteStoredImage(original.name);
  const stored = await getStoredImages();
  assert.deepEqual(stored.map(item => item.filename), ['Схема_сети.png']);
  assert.equal(await stored[0].file.text(), 'bytes');
  await deleteStoredImage('Схема_сети.png');
});

test('concurrent saves of the same original do not create a false conflict', async () => {
  const original = new File(['bytes'], 'parallel.png', { type: 'image/png' });
  await Promise.all([
    saveStoredImage(original),
    saveStoredImage(new File(['bytes'], original.name, { type: original.type })),
  ]);
  assert.equal((await getStoredImages()).length, 1);
  await deleteStoredImage(original.name);
});

test('deleting a pending upload also removes its server-normalized local copy', async () => {
  const original = new File(['bytes'], 'Два слова.png', { type: 'image/png' });
  await saveStoredImage(original);
  await saveStoredImage(new File([original], 'Два_слова.png', { type: original.type }));
  await deleteStoredImage(original.name);
  await deleteStoredImageFile(original);
  assert.deepEqual(await getStoredImages(), []);
});

test('remote deletion refuses ambiguous local originals', async () => {
  const original = new File(['original'], 'Два слова.png', { type: 'image/png' });
  const unrelated = new File(['different'], 'Два-слова.png', { type: 'image/png' });
  await saveStoredImage(original);
  await saveStoredImage(unrelated);
  await assert.rejects(deleteStoredImageByName('Два_слова.png'), /нескольким/);
  assert.deepEqual((await getStoredImages()).map(record => record.filename), [original.name, unrelated.name]);
  await deleteStoredImage(original.name);
  await deleteStoredImage(unrelated.name);
});

test('remote deletion removes an unambiguous browser filename alias', async () => {
  await saveStoredImage(new File(['original'], 'Два слова.png', { type: 'image/png' }));
  await deleteStoredImageByName('Два_слова.png');
  assert.deepEqual(await getStoredImages(), []);
});
