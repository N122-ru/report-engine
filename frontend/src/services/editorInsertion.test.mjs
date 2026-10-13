import assert from 'node:assert/strict';
import { test } from 'node:test';
import { insertEditorText } from './editorInsertion.ts';

test('raw block insertion replaces selected text and collapses the caret after the block', () => {
  const result = insertEditorText('LEFT old\ntext RIGHT', { start: 5, end: 13 }, {
    before: '\n| A |\n', replaceSelection: true,
  });
  assert.equal(result.content, 'LEFT \n| A |\n RIGHT');
  assert.deepEqual(result.selection, { start: 12, end: 12 });
});

test('raw insertion at a caret preserves both sides of the document', () => {
  const result = insertEditorText('LEFT RIGHT', { start: 5, end: 5 }, {
    before: 'TABLE\n', replaceSelection: true,
  });
  assert.equal(result.content, 'LEFT TABLE\nRIGHT');
  assert.deepEqual(result.selection, { start: 11, end: 11 });
});

test('formatting wraps selected text and leaves the inner text selected', () => {
  const result = insertEditorText('LEFT bold RIGHT', { start: 5, end: 9 }, {
    before: '**', after: '**', defaultText: 'placeholder',
  });
  assert.equal(result.content, 'LEFT **bold** RIGHT');
  assert.deepEqual(result.selection, { start: 7, end: 11 });
});

test('formatting an empty selection inserts and selects the default text', () => {
  const result = insertEditorText('AB', { start: 1, end: 1 }, {
    before: '$', after: '$', defaultText: 'n=8',
  });
  assert.equal(result.content, 'A$n=8$B');
  assert.deepEqual(result.selection, { start: 2, end: 5 });
});

test('existing image insertion preserves selected text after the image', () => {
  const before = '\n![caption](image.png)\n';
  const result = insertEditorText('LEFT selected RIGHT', { start: 5, end: 13 }, { before });
  assert.equal(result.content, `LEFT ${before}selected RIGHT`);
  assert.deepEqual(result.selection, { start: 5 + before.length, end: 13 + before.length });
});

test('a saved selection is clamped when the current document is shorter', () => {
  const result = insertEditorText('new', { start: 10, end: 20 }, {
    before: 'TABLE', replaceSelection: true,
  });
  assert.equal(result.content, 'newTABLE');
  assert.deepEqual(result.selection, { start: 8, end: 8 });
});
