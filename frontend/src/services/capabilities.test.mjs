import assert from 'node:assert/strict';
import { test } from 'node:test';
import { getRuntimeCapabilities } from './capabilities.ts';

test('getRuntimeCapabilities reports a runtime without a PDF converter', async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response(JSON.stringify({
    pdf_export: false,
    pdf_converter: null,
  }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  try {
    assert.deepEqual(await getRuntimeCapabilities(), {
      pdf_export: false,
      pdf_converter: null,
    });
  } finally {
    globalThis.fetch = previousFetch;
  }
});
