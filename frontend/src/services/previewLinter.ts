import { useMemo } from 'react';
import { formatReference } from './bibliography';
import { extractMarkdownImageSources } from './markdown';
import { isExternalImageRef, resolveImageName } from './imageRefs';
import type { ReportMetadata } from '../types';

export interface PreviewLinterStatus {
  score: number;
  isValid: boolean;
  errors: string[];
  warnings: string[];
  metrics: {
    margins: { left: number; right: number; top: number; bottom: number };
    estPages: number;
    figuresCount: number;
    tablesCount: number;
    listingsCount: number;
  };
}

export const FIGURE_NUM_RE = /^(?:рисунок|рис\.?)\s*(\d+(?:\.\d+)*)/i;
export const TABLE_NUM_RE = /^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)/i;

export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function assignCaptionNumber(
  used: Set<string>,
  auto: { value: number },
  explicit: string | null,
): string {
  if (explicit !== null) {
    used.add(explicit);
    return explicit;
  }
  do {
    auto.value++;
  } while (used.has(String(auto.value)));
  used.add(String(auto.value));
  return String(auto.value);
}

/** Compute the lightweight compliance summary shown beside the A4 preview. */
export function useLinterStatus(
  content: string,
  meta: ReportMetadata,
  images: File[],
): PreviewLinterStatus {
  return useMemo(() => {
    const errors: string[] = [];
    const warnings: string[] = [];
    const lines = content.split('\n');

    let consecutiveEmpty = 0;
    let figuresCount = 0;
    let tableBlocks = 0;
    let listingsCount = 0;
    let inCode = false;
    let codeHasContent = false;
    let fenceChar: '`' | '~' | null = null;
    let fenceLength = 0;
    let tableRun = 0;

    const flushTableRun = () => {
      if (tableRun >= 2) tableBlocks++;
      tableRun = 0;
    };

    lines.forEach((line, index) => {
      const trimmed = line.trim();

      // Detect fences first so code lines are excluded from prose checks.
      const fenceMatch = trimmed.match(/^(`{3,}|~{3,})/);
      const closesFence = Boolean(fenceMatch && inCode && fenceMatch[1][0] === fenceChar
        && fenceMatch[1].length >= fenceLength && trimmed.slice(fenceMatch[1].length).trim() === '');
      if (fenceMatch && (!inCode || closesFence)) {
        if (!inCode) {
          inCode = true;
          codeHasContent = false;
          fenceChar = fenceMatch[1][0] as '`' | '~';
          fenceLength = fenceMatch[1].length;
        } else {
          inCode = false;
          fenceChar = null;
          fenceLength = 0;
          if (codeHasContent) listingsCount++;
        }
        flushTableRun();
        if (!trimmed) {
          consecutiveEmpty++;
        } else {
          if (consecutiveEmpty >= 3) {
            errors.push(`Обнаружено ${consecutiveEmpty} пустых строк подряд (строка ${index - consecutiveEmpty + 1}). По ГОСТ верстка пустыми строками запрещена.`);
          }
          consecutiveEmpty = 0;
        }
        return;
      }
      if (inCode) {
        if (trimmed) codeHasContent = true;
        return;
      }

      if (!trimmed) {
        consecutiveEmpty++;
        flushTableRun();
      } else {
        if (consecutiveEmpty >= 3) {
          errors.push(`Обнаружено ${consecutiveEmpty} пустых строк подряд (строка ${index - consecutiveEmpty + 1}). По ГОСТ верстка пустыми строками запрещена.`);
        }
        consecutiveEmpty = 0;
      }

      if (trimmed.startsWith('#')) {
        flushTableRun();
        if (trimmed.endsWith('.')) {
          errors.push(`Точка в конце заголовка: «${trimmed}». Запрещено ГОСТ 7.32.`);
        }
      }

      const imageHits = line.match(/!\[[^\]]*\]\([^)]+\)/g);
      if (imageHits) {
        flushTableRun();
        figuresCount += imageHits.length;
        if (trimmed.includes(' - ')) {
          errors.push('В подписи к рисунку используется дефис (-) вместо тире (—).');
        }
        if (trimmed.endsWith('.)') || trimmed.endsWith('. ]') || trimmed.includes('.](')) {
          errors.push('Точка в конце подписи рисунка запрещена по ГОСТ 7.32.');
        }
      }

      if (trimmed.startsWith('|')) {
        tableRun++;
      } else {
        flushTableRun();
      }
    });
    flushTableRun();
    if (inCode && codeHasContent) listingsCount++;

    // Match backend REFERENCE/NUMBERING checks, excluding fenced code.
    const plainText = content.split(/(?:```|~~~)/).filter((_, index) => index % 2 === 0).join('\n');
    const figUsed = new Set<string>();
    const figAuto = { value: 0 };
    const figNums: string[] = [];
    for (const image of extractMarkdownImageSources(content)) {
      figNums.push(assignCaptionNumber(figUsed, figAuto, extractExplicitNumber(image.alt, FIGURE_NUM_RE)));
    }

    const tblUsed = new Set<string>();
    const tblAuto = { value: 0 };
    const tblNums: string[] = [];
    const plainLines = plainText.split('\n');
    let lineIndex = 0;
    let lastHeading = '';
    while (lineIndex < plainLines.length) {
      const plainLine = plainLines[lineIndex].trim();
      if (plainLine.startsWith('#')) {
        lastHeading = plainLine.replace(/^#+\s*/, '');
      } else if (plainLine.startsWith('|')) {
        let explicitTable: string | null = null;
        if (lineIndex > 0) {
          const previousLine = plainLines[lineIndex - 1].trim();
          const caption = previousLine.match(/^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)/i);
          if (caption) explicitTable = caption[1];
        }
        if (explicitTable === null && lastHeading && /таблиц/i.test(lastHeading)) {
          explicitTable = extractExplicitNumber(lastHeading, TABLE_NUM_RE);
        }
        tblNums.push(assignCaptionNumber(tblUsed, tblAuto, explicitTable));
        while (lineIndex < plainLines.length && plainLines[lineIndex].trim().startsWith('|')) lineIndex++;
        continue;
      }
      lineIndex++;
    }

    const textWithoutImages = plainText.replace(/!\[.*?\]\(.*?\)/g, '');
    const textForRefs = textWithoutImages
      .split('\n')
      .filter(line => !line.trim().match(/^(?:рисунок|рис\.?)\s+\d+(?:\.\d+)*(?:\s*[:–—-]|\s*$)/i)
        && !line.trim().match(/^(?:таблица|табл\.?)\s*\d+\s*[:–—.-]/i)
        && !(line.trim().length < 80 && line.trim().match(/^(?:таблица|табл\.?)\s+\d+\b/i)))
      .join('\n')
      .toLowerCase();

    const countRefOccurrences = (pattern: RegExp) => (textForRefs.match(pattern) || []).length;
    const referencedFigures = new Set<string>();
    const figureRefPattern = /(?:рисун(?:ок|ка|ку|ком|ке|ки|ках|ков|ками)|рис\.)\s+(\d+(?:\.\d+)*)(?:\s*[–—-]\s*(\d+(?:\.\d+)*))?/g;
    for (const match of textForRefs.matchAll(figureRefPattern)) {
      referencedFigures.add(match[1]);
      if (match[2]) {
        const start = match[1].split('.');
        const end = match[2].split('.');
        if (start.slice(0, -1).join('.') === end.slice(0, -1).join('.')) {
          const first = Number(start[start.length - 1]);
          const last = Number(end[end.length - 1]);
          if (last >= first && last - first <= 100) {
            for (let number = first; number <= last; number++) {
              referencedFigures.add([...start.slice(0, -1), String(number)].join('.'));
            }
          }
        }
      }
    }

    for (const number of Array.from(new Set(figNums))) {
      if (!referencedFigures.has(number)) {
        warnings.push(`В тексте нет ссылки на «Рисунок ${number}». По ГОСТ 7.32 на все иллюстрации должны быть ссылки.`);
      }
      if (figNums.filter(item => item === number).length > 1) {
        warnings.push(`Дублирующийся номер подписи: «Рисунок ${number}». Пронумеруйте иллюстрации без повторов.`);
      }
    }

    const compoundGroups = new Map<string, Set<number>>();
    for (const number of figNums) {
      if (!number.includes('.')) continue;
      const parts = number.split('.');
      const ordinal = Number(parts.pop());
      const prefix = parts.join('.');
      if (!compoundGroups.has(prefix)) compoundGroups.set(prefix, new Set());
      compoundGroups.get(prefix)!.add(ordinal);
    }
    for (const [prefix, numbers] of compoundGroups) {
      if (numbers.size < 2) continue;
      const last = Math.max(...numbers);
      if (last > 100) continue;
      for (let number = 1; number <= last; number++) {
        if (!numbers.has(number)) warnings.push(`В группе рисунков пропущен номер «${prefix}.${number}».`);
      }
    }

    for (const number of Array.from(new Set(tblNums))) {
      const hits = countRefOccurrences(new RegExp(
        `таблиц(?:а|ы|е|у|ей|ам|ах)\\s+${escapeRegExp(number)}\\b|табл\\.\\s*${escapeRegExp(number)}\\b`, 'g',
      ));
      if (hits === 0) warnings.push(`В тексте нет ссылки на «Таблицу ${number}».`);
      if (tblNums.filter(item => item === number).length > 1) {
        warnings.push(`Дублирующийся номер подписи: «Таблица ${number}». Пронумеруйте таблицы без повторов.`);
      }
    }

    const knownNames = images.map(file => file.name);
    const missingImageSources: string[] = [];
    const seenImageSources = new Set<string>();
    for (const image of extractMarkdownImageSources(content)) {
      const source = image.src.trim().replace(/^<|>$/g, '');
      if (!source || seenImageSources.has(source)) continue;
      seenImageSources.add(source);
      if (isExternalImageRef(source)) {
        warnings.push(`Изображение «${source}» нельзя встроить в DOCX/PDF из внешнего или data/blob-источника.`);
      } else if (!resolveImageName(source, knownNames)) {
        missingImageSources.push(source);
      }
    }
    for (const source of missingImageSources) {
      warnings.push(`Изображение «${source}» упомянуто в тексте, но файл не прикреплён: в документ попадёт плейсхолдер вместо рисунка.`);
    }
    for (const file of images) {
      const used = Array.from(seenImageSources).some(source => {
        let decoded = source;
        try {
          decoded = decodeURIComponent(source);
        } catch {
          // Keep the original source when it is not valid URI encoding.
        }
        return resolveImageName(decoded, knownNames) === file.name;
      });
      if (!used) warnings.push(`Прикреплённое изображение «${file.name}» не вставлено в отчёт.`);
    }

    const sourcesSectionFound = /(?:список|перечень)\s+(?:использованных\s+|основных\s+)?(источников|литературы)/i.test(plainText)
      || (meta.references || []).length > 0;
    if (sourcesSectionFound) {
      const bibRefs = plainText.match(/\[\s*\d+(?:[\s,–-]\s*\d+)*(?:\s*,\s*с\.\s*\d+)?\s*\]/g);
      if (!bibRefs || bibRefs.length === 0) {
        warnings.push('В отчете присутствует раздел «Список источников», однако в тексте отсутствуют ссылки в квадратных скобках (например, [1]).');
      }
    }

    const requiredSections: [string, RegExp][] = [
      ['Цель', /^#{1,6}\s+(?:\d+(?:\.\d+)*\s+)?цел(?:ь|и)(?:\s|:|$)/i],
      ['Ход работы', /^#{1,6}\s+(?:\d+(?:\.\d+)*\s+)?ход работы(?:\s|:|$)/i],
      ['Вывод', /^#{1,6}\s+(?:\d+(?:\.\d+)*\s+)?вывод(?:ы|ов)?(?:\s|:|$)/i],
    ];
    const foundSections = requiredSections.filter(([, pattern]) => content.split('\n').some(line => pattern.test(line.trim())));
    if (foundSections.length > 0) {
      for (const [name, pattern] of requiredSections) {
        if (!content.split('\n').some(line => pattern.test(line.trim()))) {
          warnings.push(`В отчете есть разделы, но отсутствует обязательный раздел «${name}».`);
        }
      }
    }

    const totalWords = content.split(/\s+/).filter(Boolean).length
      + (meta.references || []).reduce((sum, reference) => sum + formatReference(reference).split(/\s+/).filter(Boolean).length, 0);
    const WORDS_PER_PAGE = 220;
    const PAGES_PER_FIGURE = 0.4;
    const PAGES_PER_TABLE = 0.3;
    const estPages = Math.max(1, 1 + Math.round(totalWords / WORDS_PER_PAGE
      + figuresCount * PAGES_PER_FIGURE + (tableBlocks + listingsCount) * PAGES_PER_TABLE));

    const rawScore = 100 - (errors.length * 15) - (warnings.length * 4);
    return {
      score: Math.max(0, Math.min(100, rawScore)),
      isValid: errors.length === 0,
      errors,
      warnings,
      metrics: {
        margins: { left: 30, right: 15, top: 20, bottom: 20 },
        estPages,
        figuresCount,
        tablesCount: tableBlocks,
        listingsCount,
      },
    };
  }, [content, meta.references, images]);
}

export function extractExplicitNumber(text: string, pattern: RegExp): string | null {
  const match = (text || '').trim().match(pattern);
  return match?.[1] || null;
}
