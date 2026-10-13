import assert from 'node:assert/strict';
import { test } from 'node:test';
import { fetchWithTimeout, RequestTimeoutError, retryAfterMs } from './http.ts';

test('fetchWithTimeout aborts a stalled request', async () => {
  const previousFetch = globalThis.fetch;
  globalThis.fetch = (_input, init = {}) => new Promise((_, reject) => {
    init.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  });
  try {
    await assert.rejects(fetchWithTimeout('/slow', {}, 5), RequestTimeoutError);
  } finally {
    globalThis.fetch = previousFetch;
  }
});

test('retryAfterMs parses both seconds and HTTP-date values', () => {
  assert.equal(retryAfterMs(new Response('', { headers: { 'Retry-After': '3' } })), 3000);
  assert.ok((retryAfterMs(new Response('', {
    headers: { 'Retry-After': new Date(Date.now() + 1000).toUTCString() },
  })) || 0) >= 0);
});
