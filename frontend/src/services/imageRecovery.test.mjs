import 'fake-indexeddb/auto';
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { recoverSessionImages } from './imageRecovery.ts';
import { deleteStoredImage, getStoredImages, imageSha256, saveStoredImage } from './imageStore.ts';

const mockServer = (initial = {}) => {
  const files = new Map(Object.entries(initial));
  let uploads = 0;
  let downloads = 0;
  globalThis.fetch = async (url, options = {}) => {
    const name = decodeURIComponent(String(url).split('/').pop());
    if (options.method === 'POST') {
      assert.match(String(url), /restoring=true/);
      uploads += 1;
      const uploaded = [];
      for (const file of options.body.getAll('files')) {
        if (files.has(file.name)) return Response.json({ detail: 'duplicate' }, { status: 400 });
        files.set(file.name, file);
        uploaded.push({ filename: file.name, size_bytes: file.size, url: `/api/session/tok_test/images/${file.name}` });
      }
      return Response.json({ uploaded });
    }
    downloads += 1;
    const file = files.get(name);
    return file ? new Response(file, { headers: { 'Content-Type': file.type } }) : new Response('', { status: 404 });
  };
  return {
    files,
    get uploads() { return uploads; },
    get downloads() { return downloads; },
    list: () => [...files].map(([filename, file]) => ({ filename, size_bytes: file.size, mime_type: file.type })),
  };
};

test('restores browser originals into an empty server session', async () => {
  const original = new File(['original bytes'], 'local.png', { type: 'image/png' });
  await saveStoredImage(original);
  const server = mockServer();
  const recovered = await recoverSessionImages('tok_test', server.list());
  assert.equal(server.uploads, 1);
  assert.equal(await server.files.get(original.name).text(), 'original bytes');
  assert.deepEqual(recovered.map(file => file.name), [original.name]);
  await deleteStoredImage(original.name);
});

test('agent image is copied into browser storage before it is shown', async () => {
  const agentImage = new File(['agent bytes'], 'agent.png', { type: 'image/png' });
  const server = mockServer({ [agentImage.name]: agentImage });
  const recovered = await recoverSessionImages('tok_test', server.list());
  assert.equal(server.uploads, 0);
  assert.equal(await recovered[0].text(), 'agent bytes');
  assert.equal((await getStoredImages())[0].filename, agentImage.name);
  await deleteStoredImage(agentImage.name);
});

test('matching manifest hash reuses a local image without downloading it', async () => {
  const original = new File(['unchanged bytes'], 'cached.png', { type: 'image/png' });
  await saveStoredImage(original);
  const server = mockServer({ [original.name]: new File(['unchanged bytes'], original.name, { type: 'image/png' }) });
  const manifest = [{
    filename: original.name,
    size_bytes: original.size,
    mime_type: original.type,
    sha256: await imageSha256(original),
  }];

  const recovered = await recoverSessionImages('tok_test', manifest);

  assert.equal(server.downloads, 0);
  assert.equal(await recovered[0].text(), 'unchanged bytes');
  await deleteStoredImage(original.name);
});

test('does not save a truncated server response as an original', async () => {
  const image = new File(['short'], 'truncated.png', { type: 'image/png' });
  const server = mockServer({ [image.name]: image });
  const manifest = server.list();
  manifest[0].size_bytes += 1;
  await assert.rejects(recoverSessionImages('tok_test', manifest), /Размер/);
  assert.deepEqual(await getStoredImages(), []);
});

test('a matching sanitized name does not upload or duplicate the image', async () => {
  const original = new File(['same bytes'], 'Схема сети.png', { type: 'image/png' });
  const serverImage = new File(['same bytes'], 'Схема_сети.png', { type: 'image/png' });
  await saveStoredImage(original);
  const server = mockServer({ [serverImage.name]: serverImage });
  const recovered = await recoverSessionImages('tok_test', server.list());
  assert.equal(server.uploads, 0);
  assert.deepEqual(recovered.map(file => file.name), [serverImage.name]);
  assert.deepEqual((await getStoredImages()).map(record => record.filename), [serverImage.name]);
  await deleteStoredImage(serverImage.name);
});

test('same image name with different bytes blocks recovery without replacement', async () => {
  const original = new File(['original'], 'conflict.png', { type: 'image/png' });
  await saveStoredImage(original);
  const server = mockServer({ [original.name]: new File(['cropped'], original.name, { type: 'image/png' }) });
  await assert.rejects(recoverSessionImages('tok_test', server.list()), /различаются/);
  assert.equal(server.uploads, 0);
  assert.equal(await (await getStoredImages())[0].file.text(), 'original');
  await deleteStoredImage(original.name);
});

test('different server filenames with the same normalized spelling remain distinct', async () => {
  const first = new File(['first'], 'a-b.png', { type: 'image/png' });
  const second = new File(['second'], 'a_b.png', { type: 'image/png' });
  await saveStoredImage(first);
  await saveStoredImage(second);
  const server = mockServer({ [first.name]: first, [second.name]: second });
  const recovered = await recoverSessionImages('tok_test', server.list());
  assert.equal(recovered.length, 2);
  assert.deepEqual((await getStoredImages()).map(record => record.filename), [first.name, second.name]);
  await deleteStoredImage(first.name);
  await deleteStoredImage(second.name);
});

test('failed upload keeps the browser original for retry', async () => {
  const original = new File(['original'], 'offline.png', { type: 'image/png' });
  await saveStoredImage(original);
  mockServer();
  globalThis.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(recoverSessionImages('tok_test', []), /offline/);
  assert.equal(await (await getStoredImages())[0].file.text(), 'original');
  await deleteStoredImage(original.name);
});

test('an agent deletion while the tab was closed is not undone on reconnect', async () => {
  await saveStoredImage(new File(['original'], 'Удалить рисунок.png', { type: 'image/png' }));
  const server = mockServer();
  const recovered = await recoverSessionImages('tok_test', server.list(), ['Удалить_рисунок.png']);
  assert.deepEqual(recovered, []);
  assert.equal(server.uploads, 0);
  assert.deepEqual(await getStoredImages(), []);
});
