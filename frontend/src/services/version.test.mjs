import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getVersionInfo } from './update.ts';

test('getVersionInfo returns the server version contract', async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    version: '0.1.0',
    update: { status: 'current', latest_version: '0.1.0', release_url: null },
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  try {
    assert.deepEqual(await getVersionInfo(), {
      version: '0.1.0',
      update: { status: 'current', latest_version: '0.1.0', release_url: null },
    });
  } finally {
    globalThis.fetch = previousFetch;
  }
});
