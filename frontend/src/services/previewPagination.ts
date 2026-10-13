import { parseReportInline, type InlinePart } from './markdown.ts';

const PAGE_CONTENT_WIDTH = 595 - 85 - 43;
const CHARACTER_WIDTH = 8;
const LINE_HEIGHT = 21;
const FIRST_LINE_INDENT = 35.4;
// Leave room for rounding differences between the estimate and browser layout.
const MAX_PAGE_CONTENT_HEIGHT = 700 - 10;

/** A Markdown preview block with its estimated unscaled height. */
export interface ParsedBlock {
  id: string;
  type: 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6' | 'p' | 'list' | 'image' | 'table' | 'code' | 'math' | 'bibhead' | 'bibref';
  data: any;
  estHeight: number;
}

interface PreviewParagraphData {
  text: string;
  lines: InlinePart[][];
  linesEst: number;
  noIndent: boolean;
  isStandaloneCode: boolean;
}

/** Read table cells without dropping empty cells or an optional final pipe. */
export function splitPreviewTableRow(row: string): string[] {
  return row.trim().replace(/^\|/, '').replace(/(?<!\\)\|$/, '')
    .split(/(?<!\\)\|/).map(cell => cell.replace(/\\\|/g, '|').trim());
}

function wrapInlineParts(parts: InlinePart[], firstLineIndent = 0, width = PAGE_CONTENT_WIDTH): InlinePart[][] {
  const text = parts.map(part => part.text).join('');
  const ranges: { part: InlinePart; start: number; end: number }[] = [];
  let offset = 0;
  for (const part of parts) {
    ranges.push({ part, start: offset, end: offset + part.text.length });
    offset += part.text.length;
  }
  const lines: InlinePart[][] = [];
  let start = 0;
  while (start < text.length) {
    const indent = lines.length === 0 ? firstLineIndent : 0;
    const capacity = Math.max(1, Math.floor((width - indent) / CHARACTER_WIDTH));
    let end = Math.min(text.length, start + capacity);
    if (end < text.length) {
      const space = text.lastIndexOf(' ', end);
      if (space > start) end = space + 1;
    }
    // Inline formulas are opaque: never cut their LaTeX source between pages.
    const formula = ranges.find(range => range.part.kind === 'math' && range.start < end && range.end > end);
    if (formula) end = formula.start > start ? formula.start : formula.end;
    lines.push(ranges.filter(range => range.end > start && range.start < end).map(range => ({
      ...range.part,
      text: range.part.text.slice(Math.max(0, start - range.start), end - range.start)
    })));
    start = end;
  }
  return lines.length ? lines : [[]];
}

/** Prepare conservative prose lines while retaining parsed inline formatting. */
export function createPreviewParagraph(text: string): PreviewParagraphData {
  const isExplication = /^\s*где\b/i.test(text);
  const isStandaloneCode = /^\s*`[^`]+`\s*$/.test(text);
  const noIndent = isExplication || isStandaloneCode;
  const lines = wrapInlineParts(parseReportInline(text), noIndent ? 0 : FIRST_LINE_INDENT);
  return { text, lines, linesEst: lines.length, noIndent, isStandaloneCode };
}

/** Estimate wrapped cells, the header, caption, padding and collapsed borders. */
export function estimateTableHeight(dataRows: string[], caption: string, hideCaptions = false): number {
  const rows = dataRows.map(splitPreviewTableRow);
  const columns = Math.max(1, ...rows.map(row => row.length));
  const cellWidth = PAGE_CONTENT_WIDTH / columns - 12 - 2;
  const rowsHeight = rows.reduce((sum, row) => sum + Math.max(1, ...row.map(cell =>
    wrapInlineParts(parseReportInline(cell), 0, cellWidth).length)) * LINE_HEIGHT + 13, 0);
  const captionHeight = hideCaptions ? 0 : wrapInlineParts(parseReportInline(caption)).length * LINE_HEIGHT + 4;
  return 18 + 1 + captionHeight + rowsHeight;
}

/** Distribute preview blocks over A4 pages without changing their source. */
export function paginatePreviewBlocks(allBlocks: ParsedBlock[], pageBreakBeforeH1 = false): ParsedBlock[][] {
  if (allBlocks.length === 0) return [];
  const pages: ParsedBlock[][] = [[]];
  let currentHeight = 0;
  allBlocks.forEach((block, idx) => {
    if (block.type === 'image' && block.data.layout?.page_break_before && pages[pages.length - 1].length > 0) {
      pages.push([]);
      currentHeight = 0;
    }
    if (pageBreakBeforeH1 && block.type === 'h1' && pages[pages.length - 1].length > 0) {
      pages.push([block]);
      currentHeight = block.estHeight;
      return;
    }
    // Preserve the existing keep-with-next reservation for report headings.
    const isHeading = block.type.startsWith('h') || block.type === 'bibhead';
    const nextBlock = allBlocks[idx + 1];
    const nextNeededHeight = nextBlock ? Math.min(nextBlock.estHeight, 50) : 30;
    if (isHeading && currentHeight + block.estHeight + nextNeededHeight > MAX_PAGE_CONTENT_HEIGHT && pages[pages.length - 1].length > 0) {
      pages.push([block]);
      currentHeight = block.estHeight;
      return;
    }
    if (block.type === 'bibhead' && pages[pages.length - 1].length > 0) {
      pages.push([block]);
      currentHeight = block.estHeight;
      return;
    }
    if (block.type === 'list') {
      const items = block.data.items || [];
      const startNum = Math.max(1, block.data.start || 1);
      let curChunk: any[] = [];
      let curChunkStart = startNum;
      const flushChunk = () => {
        if (curChunk.length === 0) return;
        pages[pages.length - 1].push({
          id: `${block.id}-p${pages.length}-${curChunkStart}`,
          type: 'list',
          data: { items: curChunk, start: curChunkStart },
          estHeight: curChunk.reduce((sum: number, item: any) => sum + (item.estHeight || 21), 0)
        });
        curChunk = [];
      };
      items.forEach((item: any, itemIdx: number) => {
        const height = item.estHeight || 21;
        const isPageEmpty = pages[pages.length - 1].length === 0 && curChunk.length === 0;
        if (!isPageEmpty && currentHeight + height > MAX_PAGE_CONTENT_HEIGHT) {
          flushChunk();
          pages.push([]);
          currentHeight = 0;
          curChunkStart = startNum + itemIdx;
        }
        curChunk.push(item);
        currentHeight += height;
      });
      flushChunk();
      return;
    }
    if (block.type === 'p') {
      const data = block.data.lines ? block.data : createPreviewParagraph(block.data.text || '');
      const lines: InlinePart[][] = data.lines;
      let lineOffset = 0;
      while (lineOffset < lines.length) {
        const availableLines = Math.floor((MAX_PAGE_CONTENT_HEIGHT - currentHeight) / LINE_HEIGHT);
        if (availableLines < 1) {
          pages.push([]);
          currentHeight = 0;
          continue;
        }
        const lineCount = Math.min(availableLines, lines.length - lineOffset);
        const parts = lines.slice(lineOffset, lineOffset + lineCount).flat();
        pages[pages.length - 1].push({
          ...block,
          id: `${block.id}-line${lineOffset}`,
          data: { ...data, parts, continuation: lineOffset > 0, linesEst: lineCount },
          estHeight: lineCount * LINE_HEIGHT
        });
        currentHeight += lineCount * LINE_HEIGHT;
        lineOffset += lineCount;
      }
      return;
    }
    if (currentHeight + block.estHeight > MAX_PAGE_CONTENT_HEIGHT && pages[pages.length - 1].length > 0) {
      pages.push([]);
      currentHeight = 0;
    }
    pages[pages.length - 1].push(block);
    currentHeight += block.estHeight;
  });
  return pages;
}
