import assert from 'node:assert/strict';
import { test } from 'node:test';
import {
  syncSessionToServer,
  serializeMetadata,
  metadataUpdateMessage,
  buildContentPatches,
  applyContentPatches,
} from './session.ts';

test('content patches preserve Unicode code-point positions', () => {
  const before = 'Параметр: 🙂\nСтарое значение';
  const after = 'Параметр: 🙂\nНовое значение';
  const patches = buildContentPatches(before, after);
  assert.equal(applyContentPatches(before, patches), after);
  assert.equal(patches.length, 1);
});

test('metadata comparison ignores object key order at every depth but preserves array order', () => {
  const browser = { work_theme: 'Тема', image_layouts: { 'screen.png': { align: 'right', width_percent: 72 } }, students: [{ fio: 'И.И. Иванов', group: '101' }] };
  const agent = { students: [{ group: '101', fio: 'И.И. Иванов' }], image_layouts: { 'screen.png': { width_percent: 72, align: 'right' } }, work_theme: 'Тема' };
  assert.equal(serializeMetadata(browser), serializeMetadata(agent));
  assert.notEqual(serializeMetadata({ students: ['first', 'second'] }), serializeMetadata({ students: ['second', 'first'] }));
  assert.notEqual(serializeMetadata(browser), serializeMetadata({ ...agent, work_theme: 'Новая тема' }));
});

test('image layout changes are not announced as title page changes and duplicates are silent', () => {
  const before = { work_theme: 'Тема', image_layouts: { 'screen.png': { align: 'center' } } };
  const after = { ...before, image_layouts: { 'screen.png': { align: 'right' } } };
  assert.equal(metadataUpdateMessage(before, after), 'ИИ обновил размещение рисунков');
  assert.equal(metadataUpdateMessage(after, { image_layouts: after.image_layouts, work_theme: 'Тема' }), null);
  assert.equal(metadataUpdateMessage(after, { ...after, work_theme: 'Новая тема' }), 'ИИ обновил реквизиты отчёта');
});

test('browser sync identifies the originating tab for SSE acknowledgements', async () => {
  const storage = new Map();
  globalThis.sessionStorage = {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, value),
  };
  let sent;
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async (_url, options) => {
    sent = JSON.parse(options.body);
    return Response.json({ status: 'ok', revision: 'next', meta_revision: 'meta' });
  };
  try {
    const result = await syncSessionToServer('tok_test', {
      content: 'Новая строка', expected_revision: 'current',
    });
    assert.equal(result.status, 'ok');
    assert.equal(typeof sent.client_id, 'string');
    assert.ok(sent.client_id.length > 0);
  } finally {
    globalThis.fetch = previousFetch;
  }
});
