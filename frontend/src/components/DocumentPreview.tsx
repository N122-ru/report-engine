import React, { useState, useMemo, useEffect, useRef } from 'react';
import katex from 'katex';
import { ReportMetadata } from '../types';
import { normalizeLogoMode } from '../services/profiles';
import { formatReference } from '../services/bibliography';
import { extractMarkdownImageSources, parseReportInline, type InlinePart } from '../services/markdown';
import { isExternalImageRef, resolveImageName } from '../services/imageRefs';
import { createPreviewParagraph, estimateTableHeight, paginatePreviewBlocks, splitPreviewTableRow, type ParsedBlock } from '../services/previewPagination';
import { 
  CheckCircle, XCircle, ShieldCheck, Eye, Wand2,
  ZoomIn, ZoomOut, Maximize2, SlidersHorizontal, ChevronDown
} from 'lucide-react';

interface DocumentPreviewProps {
  meta: ReportMetadata;
  content: string;
  images: File[];
  onAutofix: () => void;
  headingAlignment?: 'left' | 'center';
  onHeadingAlignmentChange?: (align: 'left' | 'center') => void;
  pageNumbering?: 'center' | 'right' | 'none';
  onPageNumberingChange?: (pos: 'center' | 'right' | 'none') => void;
  pageBreakBeforeH1?: boolean;
  onPageBreakBeforeH1Change?: (val: boolean) => void;
  onHideCaptionsChange?: (val: boolean) => void;
  latexMode?: 'omml' | 'unicode';
  onLatexModeChange?: (mode: 'omml' | 'unicode') => void;
}

// Normalize names to initials followed by surname, matching title_page.py.
function normalizeFio(fio: string): string {
  const trimmed = (fio || '').trim();
  if (!trimmed) return '';

  const capName = (str: string) => str.split('-').map(p => p.charAt(0).toUpperCase() + p.slice(1).toLowerCase()).join('-');

  // Move surname-first initials ahead of the surname.
  const mLastFirst = trimmed.match(/^([А-ЯЁа-яё-]+)\s+([А-ЯЁ]\.?)\s*([А-ЯЁ]\.?)?$/);
  if (mLastFirst) {
    const last = capName(mLastFirst[1]);
    const i1 = mLastFirst[2].replace(/\./g, '').toUpperCase() + '.';
    const i2 = mLastFirst[3] ? mLastFirst[3].replace(/\./g, '').toUpperCase() + '.' : '';
    return `${i1}${i2} ${last}`;
  }

  // Normalize initials preceding the surname.
  const mFirstLast = trimmed.match(/^([А-ЯЁ]\.?)\s*([А-ЯЁ]\.?)?\s+([А-ЯЁа-яё-]+)$/);
  if (mFirstLast) {
    const i1 = mFirstLast[1].replace(/\./g, '').toUpperCase() + '.';
    const i2 = mFirstLast[2] ? mFirstLast[2].replace(/\./g, '').toUpperCase() + '.' : '';
    const last = capName(mFirstLast[3]);
    return `${i1}${i2} ${last}`;
  }

  // Reduce full given names and patronymics to initials.
  const parts = trimmed.split(/\s+/);
  if (parts.length === 3 && !parts.some(p => p.includes('.'))) {
    const last = capName(parts[0]);
    const i1 = parts[1].charAt(0).toUpperCase() + '.';
    const i2 = parts[2].charAt(0).toUpperCase() + '.';
    return `${i1}${i2} ${last}`;
  }

  return trimmed;
}

function capitalizeCaption(caption: string): string {
  const index = [...caption].findIndex(char => /\p{L}/u.test(char));
  if (index < 0) return caption;
  const chars = [...caption];
  chars[index] = chars[index].toLocaleUpperCase();
  return chars.join('');
}

// Preview LaTeX symbols and operators mirror math_utils.py::MATH_SYMBOLS.
const GREEK_AND_SYMBOLS: Record<string, string> = {
  '\\to': '→',
  '\\rightarrow': '→',
  '\\leftarrow': '←',
  '\\leftrightarrow': '↔',
  '\\Rightarrow': '⇒',
  '\\Leftarrow': '⇐',
  '\\approx': '≈',
  '\\le': '≤',
  '\\leq': '≤',
  '\\ge': '≥',
  '\\geq': '≥',
  '\\neq': '≠',
  '\\pm': '±',
  '\\mp': '∓',
  '\\times': '×',
  '\\cdot': '·',
  '\\div': '÷',
  '\\infty': '∞',
  '\\partial': '∂',
  '\\nabla': '∇',
  '\\alpha': 'α',
  '\\beta': 'β',
  '\\gamma': 'γ',
  '\\delta': 'δ',
  '\\epsilon': 'ε',
  '\\theta': 'θ',
  '\\lambda': 'λ',
  '\\mu': 'μ',
  '\\pi': 'π',
  '\\rho': 'ρ',
  '\\sigma': 'σ',
  '\\tau': 'τ',
  '\\phi': 'φ',
  '\\omega': 'ω',
  '\\Delta': 'Δ',
  '\\Gamma': 'Γ',
  '\\Lambda': 'Λ',
  '\\Sigma': 'Σ',
  '\\Omega': 'Ω',
  '\\forall': '∀',
  '\\exists': '∃',
  '\\sum': '∑',
  '\\prod': '∏',
  '\\int': '∫',
  '\\in': '∈',
  '\\notin': '∉',
  '\\subset': '⊂',
  '\\subseteq': '⊆',
  '\\cup': '∪',
  '\\cap': '∩',
  '\\emptyset': '∅',
  '\\dots': '…',
  '\\cdots': '…',
  '\\quad': '\u00A0\u00A0',
  '\\qquad': '\u00A0\u00A0\u00A0\u00A0',
  '\\,': '\u00A0',
  '\\;': '\u00A0',
  '\\sin': 'sin',
  '\\cos': 'cos',
  '\\tan': 'tan',
  '\\cot': 'cot',
  '\\sec': 'sec',
  '\\csc': 'csc',
  '\\arcsin': 'arcsin',
  '\\arccos': 'arccos',
  '\\arctan': 'arctan',
  '\\sinh': 'sinh',
  '\\cosh': 'cosh',
  '\\tanh': 'tanh',
  '\\log': 'log',
  '\\ln': 'ln',
  '\\lg': 'lg',
  '\\lim': 'lim',
  '\\exp': 'exp',
  '\\min': 'min',
  '\\max': 'max',
  '\\sup': 'sup',
  '\\inf': 'inf',
  '\\arg': 'arg',
  '\\deg': 'deg',
  '\\dim': 'dim',
  '\\det': 'det',
  '\\gcd': 'gcd',
  '\\hom': 'hom',
  '\\ker': 'ker',
  '\\degree': '°',
  '\\circ': '°',
};

// Simplified equation text mirrors backend fallback_latex_to_unicode.
// Unicode mode uses plain text, without stacked fractions.
function fallbackLatexToUnicode(latex: string): string {
  let res = latex.trim();
  const cmds = Object.entries(GREEK_AND_SYMBOLS).sort((a, b) => b[0].length - a[0].length);
  for (const [cmd, sym] of cmds) {
    res = res.replace(new RegExp(cmd.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![a-zA-Z])', 'g'), sym);
  }
  res = res.replace(/\\frac\{([^{}]+)\}\{([^{}]+)\}/g, '($1)/($2)');
  res = res.replace(/\\sqrt\{([^{}]+)\}/g, '√($1)');
  res = res.replace(/\\(?:text|mathrm|mathbf|operatorname|mathit)\{([^{}]+)\}/g, '$1');
  res = res.replace(/\\[a-zA-Z]+/g, '');
  res = res.replace(/[{}]/g, '');
  return res;
}



// Unicode mode uses the backend's simplified text fallback.
// OMML mode previews equations with KaTeX; actual DOCX equations use OMML.
function renderMathFormula(
  latex: string, 
  mode: 'omml' | 'unicode' = 'omml',
  displayMode: boolean = false
): React.ReactNode {
  if (mode === 'unicode') {
    return <span className="font-serif text-black">{fallbackLatexToUnicode(latex)}</span>;
  }
  const clean = latex.trim();
  if (!clean) return null;

  try {
    const html = katex.renderToString(clean, {
      displayMode,
      throwOnError: false,
      output: 'html',
    });
    return (
      <span 
        className={displayMode ? "katex-display-wrapper inline-block" : "katex-inline-wrapper inline-block align-baseline"}
        dangerouslySetInnerHTML={{ __html: html }} 
      />
    );
  } catch {
    return <span className="font-serif text-black">{clean}</span>;
  }
}

// Format inline equations, emphasis, and code.
// Inline code shares the body's Times New Roman font by project policy.
function renderFormattedText(text: string, latexMode: 'omml' | 'unicode' = 'omml'): React.ReactNode {
  if (!text) return null;
  return renderInlineParts(parseReportInline(text), latexMode);
}

function renderInlineParts(parts: InlinePart[], latexMode: 'omml' | 'unicode'): React.ReactNode {
  return <>{parts.map((part, index) => {
    let node: React.ReactNode = part.kind === 'math'
      ? <span className="inline-block mx-0.5">{renderMathFormula(part.text, latexMode, false)}</span>
      : part.text;
    if (part.bold) node = <strong className="font-bold">{node}</strong>;
    if (part.italic) node = <em className="italic">{node}</em>;
    return <React.Fragment key={index}>{node}</React.Fragment>;
  })}</>;
}

// Resolve images using exact and normalized filenames.
function resolveImagePreviewUrl(
  filename: string,
  imageMap: Record<string, string>,
  images: File[]
): string | undefined {
  if (!filename || isExternalImageRef(filename)) return undefined;
  const resolved = resolveImageName(filename, images.map(image => image.name));
  return resolved ? imageMap[resolved] || imageMap[resolved.toLowerCase()] : undefined;
}

// Listing captions mirror backend clean_listing_caption (typography.py).
// Accept colon/title/parenthesized names, otherwise use the source-code language.
// Trim fence info like markdown-it and preserve language names such as c++.
function cleanListingCaption(info: string, n: number): string {
  const raw = (info || '').trim();
  if (raw.includes(':')) {
    const name = raw.split(':', 2)[1].trim();
    if (name) return `Листинг\u00A0${n} — ${name}`;
  }
  const titleMatch = raw.match(/title=["'](.*?)["']/);
  if (titleMatch && titleMatch[1].trim()) {
    return `Листинг\u00A0${n} — ${titleMatch[1].trim()}`;
  }
  const parenMatch = raw.match(/\((.*?)\)/);
  if (parenMatch && parenMatch[1].trim()) {
    return `Листинг\u00A0${n} — ${parenMatch[1].trim()}`;
  }
  const lang = raw.split(/\s+/)[0] || '';
  if (lang) return `Листинг\u00A0${n} — Исходный код (${lang})`;
  return `Листинг\u00A0${n} — Исходный код`;
}

// Caption numbering mirrors markdown_parser.py: preserve author numbers
// verbatim, including compound numbers in any order. Use the next free
// number only when no author number is supplied.
const FIGURE_NUM_RE = /^(?:рисунок|рис\.?)\s*(\d+(?:\.\d+)*)/i;
const TABLE_NUM_RE = /^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)/i;

function extractExplicitNumber(text: string, pattern: RegExp): string | null {
  const m = (text || '').trim().match(pattern);
  if (!m) return null;
  return m[1] || null;
}

function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function assignCaptionNumber(used: Set<string>, auto: { value: number }, explicit: string | null): string {
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

export const DocumentPreview: React.FC<DocumentPreviewProps> = ({
  meta,
  content,
  images,
  onAutofix,
  headingAlignment = meta.heading_alignment || 'center',
  onHeadingAlignmentChange,
  pageNumbering = meta.page_numbering || 'center',
  onPageNumberingChange,
  pageBreakBeforeH1 = meta.page_break_before_h1 ?? false,
  onPageBreakBeforeH1Change,
  onHideCaptionsChange,
  latexMode = meta.latex_mode || 'omml',
  onLatexModeChange
}) => {
  const [activeTab, setActiveTab] = useState<'preview' | 'linter'>('preview');
  const [zoom, setZoom] = useState<number>(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      return Math.min(1, Math.max(0.35, Math.round(((window.innerWidth - 32) / 595) * 100) / 100));
    }
    return 1;
  });
  const [isFitWidth, setIsFitWidth] = useState<boolean>(() => {
    if (typeof window !== 'undefined' && window.innerWidth < 768) {
      return true;
    }
    return false;
  });
  const [isSettingsOpen, setIsSettingsOpen] = useState<boolean>(false);
  const previewContainerRef = useRef<HTMLDivElement | null>(null);
  const settingsRef = useRef<HTMLDivElement | null>(null);

  // Close the formatting menu when clicking outside it.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (settingsRef.current && !settingsRef.current.contains(e.target as Node)) {
        setIsSettingsOpen(false);
      }
    };
    if (isSettingsOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [isSettingsOpen]);

  // Fit preview scale to the container width.
  const updateFitWidth = () => {
    if (!previewContainerRef.current) return;
    const containerWidth = previewContainerRef.current.clientWidth;
    if (containerWidth <= 0) return;
    const padding = containerWidth < 640 ? 16 : containerWidth < 768 ? 32 : 48;
    const availWidth = Math.max(240, containerWidth - padding);
    const newScale = Math.min(2.0, Math.max(0.35, Math.round((availWidth / 595) * 100) / 100));
    setZoom(newScale);
  };

  useEffect(() => {
    if (!isFitWidth || !previewContainerRef.current) return;
    updateFitWidth();

    let ro: ResizeObserver | null = null;
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          if (entry.contentRect.width > 0) {
            updateFitWidth();
          }
        }
      });
      ro.observe(previewContainerRef.current);
    }

    const handleResize = () => updateFitWidth();
    window.addEventListener('resize', handleResize);
    return () => {
      if (ro) ro.disconnect();
      window.removeEventListener('resize', handleResize);
    };
  }, [isFitWidth]);

  const toggleFitWidth = () => {
    if (isFitWidth) {
      setIsFitWidth(false);
      setZoom(1);
    } else {
      setIsFitWidth(true);
      updateFitWidth();
    }
  };

  const handleZoomChange = (delta: number) => {
    setIsFitWidth(false);
    setZoom(prev => Math.min(2.0, Math.max(0.4, Math.round((prev + delta) * 10) / 10)));
  };

  const resetZoom = () => {
    setIsFitWidth(false);
    setZoom(1);
  };

  // Provide quick client-side GOST 7.32 checks; /api/verify is authoritative.
  // Keep score formulas and constants aligned with backend linter.py.
  const hasReportText = content.trim().length > 0;
  const linterStatus = useMemo(() => {
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

    lines.forEach((l, idx) => {
      const s = l.trim();

      // Detect fences first so code lines are excluded from prose checks.
      const fenceMatch = s.match(/^(`{3,}|~{3,})/);
      const closesFence = Boolean(fenceMatch && inCode && fenceMatch[1][0] === fenceChar
        && fenceMatch[1].length >= fenceLength && s.slice(fenceMatch[1].length).trim() === '');
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
          // Empty fences are not listings, matching the backend.
          if (codeHasContent) listingsCount++;
        }
        flushTableRun();
        if (!s) {
          consecutiveEmpty++;
        } else {
          if (consecutiveEmpty >= 3) {
            errors.push(`Обнаружено ${consecutiveEmpty} пустых строк подряд (строка ${idx - consecutiveEmpty + 1}). По ГОСТ верстка пустыми строками запрещена.`);
          }
          consecutiveEmpty = 0;
        }
        return;
      }
      if (inCode) {
        if (s) codeHasContent = true;
        return;
      }

      if (!s) {
        consecutiveEmpty++;
        flushTableRun();
      } else {
        if (consecutiveEmpty >= 3) {
          errors.push(`Обнаружено ${consecutiveEmpty} пустых строк подряд (строка ${idx - consecutiveEmpty + 1}). По ГОСТ верстка пустыми строками запрещена.`);
        }
        consecutiveEmpty = 0;
      }

      if (s.startsWith('#')) {
        flushTableRun();
        if (s.endsWith('.')) {
          errors.push(`Точка в конце заголовка: «${s}». Запрещено ГОСТ 7.32.`);
        }
      }

      // Count image references outside code, matching the backend.
      // Caption prefixes in alt text do not affect the figure count.
      const imgHits = l.match(/!\[[^\]]*\]\([^)]+\)/g);
      if (imgHits) {
        flushTableRun();
        figuresCount += imgHits.length;
        if (s.includes(' - ')) {
          errors.push(`В подписи к рисунку используется дефис (-) вместо тире (—).`);
        }
        if (s.endsWith('.)') || s.endsWith('. ]') || s.includes('.](')) {
          errors.push(`Точка в конце подписи рисунка запрещена по ГОСТ 7.32.`);
        }
      }

      // Count consecutive table rows as one table, including separator rows,
      // matching the backend's table count rather than its row count.
      if (s.startsWith('|')) {
        tableRun++;
      } else {
        flushTableRun();
      }
    });
    flushTableRun();
    // An unclosed nonempty fence is one listing, as in the backend parser.
    if (inCode && codeHasContent) listingsCount++;

    // Match backend REFERENCE/NUMBERING checks, excluding fenced code.
    // Preserve manual compound numbers; otherwise use the next free number.
    // Recognize Russian case inflections in figure and table references.
    const plainText = content.split(/(?:```|~~~)/).filter((_, i) => i % 2 === 0).join('\n');
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
    let pIdx = 0;
    let lastHText = '';
    while (pIdx < plainLines.length) {
      const pl = plainLines[pIdx].trim();
      if (pl.startsWith('#')) {
        lastHText = pl.replace(/^#+\s*/, '');
      } else if (pl.startsWith('|')) {
        let explicitTbl: string | null = null;
        if (pIdx > 0) {
          const prevL = plainLines[pIdx - 1].trim();
          const mCap = prevL.match(/^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)/i);
          if (mCap) {
            explicitTbl = mCap[1];
          }
        }
        if (explicitTbl === null && lastHText && /таблиц/i.test(lastHText)) {
          explicitTbl = extractExplicitNumber(lastHText, TABLE_NUM_RE);
        }
        tblNums.push(assignCaptionNumber(tblUsed, tblAuto, explicitTbl));
        while (pIdx < plainLines.length && plainLines[pIdx].trim().startsWith('|')) {
          pIdx++;
        }
        continue;
      }
      pIdx++;
    }

    // Exclude image tags and table captions when searching prose for references.
    const textWithoutImages = plainText.replace(/!\[.*?\]\(.*?\)/g, '');
    const textForRefs = textWithoutImages
      .split('\n')
      .filter(l => !l.trim().match(/^(?:рисунок|рис\.?)\s+\d+(?:\.\d+)*(?:\s*[:–—-]|\s*$)/i) && !l.trim().match(/^(?:таблица|табл\.?)\s*\d+\s*[:–—.\-]/i) && !(l.trim().length < 80 && l.trim().match(/^(?:таблица|табл\.?)\s+\d+\b/i)))
      .join('\n')
      .toLowerCase();

    const countRefOccurrences = (re: RegExp) => (textForRefs.match(re) || []).length;
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
            for (let i = first; i <= last; i++) referencedFigures.add([...start.slice(0, -1), String(i)].join('.'));
          }
        }
      }
    }

    for (const n of Array.from(new Set(figNums))) {
      if (!referencedFigures.has(n)) {
        warnings.push(`В тексте нет ссылки на «Рисунок ${n}». По ГОСТ 7.32 на все иллюстрации должны быть ссылки.`);
      }
      if (figNums.filter(x => x === n).length > 1) {
        warnings.push(`Дублирующийся номер подписи: «Рисунок ${n}». Пронумеруйте иллюстрации без повторов.`);
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
      for (let n = 1; n <= last; n++) {
        if (!numbers.has(n)) warnings.push(`В группе рисунков пропущен номер «${prefix}.${n}».`);
      }
    }

    for (const n of Array.from(new Set(tblNums))) {
      const nEsc = escapeRegExp(n);
      const hits = countRefOccurrences(new RegExp(`таблиц(?:а|ы|е|у|ей|ам|ах)\\s+${nEsc}\\b|табл\\.\\s*${nEsc}\\b`, 'g'));
      if (hits === 0) {
        warnings.push(`В тексте нет ссылки на «Таблицу ${n}».`);
      }
      if (tblNums.filter(x => x === n).length > 1) {
        warnings.push(`Дублирующийся номер подписи: «Таблица ${n}». Пронумеруйте таблицы без повторов.`);
      }
    }

    // Warn about missing image attachments before they become export placeholders.
    const knownNames = images.map(file => file.name);
    const resolveKnown = (src: string): boolean => {
      const raw = (src || '').trim().replace(/^<|>$/g, '');
      if (!raw) return true;
      if (isExternalImageRef(raw)) {
        return true;
      }
      return Boolean(resolveImageName(raw, knownNames));
    };
    const missingSrcs: string[] = [];
    const seenImgSrcs = new Set<string>();
    for (const image of extractMarkdownImageSources(content)) {
      const src = image.src.trim().replace(/^<|>$/g, '');
      if (!src || seenImgSrcs.has(src)) continue;
      seenImgSrcs.add(src);
      if (isExternalImageRef(src)) {
        warnings.push(`Изображение «${src}» нельзя встроить в DOCX/PDF из внешнего или data/blob-источника.`);
        continue;
      }
      if (!resolveKnown(src)) missingSrcs.push(src);
    }
    for (const src of missingSrcs) {
      warnings.push(`Изображение «${src}» упомянуто в тексте, но файл не прикреплён: в документ попадёт плейсхолдер вместо рисунка.`);
    }
    for (const file of images) {
      if (![...seenImgSrcs].some(src => {
        let decoded = src;
        try { decoded = decodeURIComponent(src); } catch {}
        return decoded.split(/[/\\]/).pop() === file.name;
      })) warnings.push(`Прикреплённое изображение «${file.name}» не вставлено в отчёт.`);
    }

    const sourcesSectionFound = /(?:список|перечень)\s+(?:использованных\s+|основных\s+)?(источников|литературы)/i.test(plainText)
      || (meta.references || []).length > 0;
    if (sourcesSectionFound) {
      const bibRefs = plainText.match(/\[\s*\d+(?:[\s,\–\-]\s*\d+)*(?:\s*,\s*с\.\s*\d+)?\s*\]/g);
      if (!bibRefs || bibRefs.length === 0) {
        warnings.push('В отчете присутствует раздел «Список источников», однако в тексте отсутствуют ссылки в квадратных скобках (например, [1]).');
      }
    }

    // Require standard sections only when the author uses that structure.
    // Mirror backend linter.py patterns; JS word boundaries exclude Cyrillic.
    const reqSections: [string, RegExp][] = [
      ['Цель', /^#{1,6}\s+(?:\d+(?:\.\d+)*\s+)?цел(?:ь|и)(?:\s|:|$)/i],
      ['Ход работы', /^#{1,6}\s+(?:\d+(?:\.\d+)*\s+)?ход работы(?:\s|:|$)/i],
      ['Вывод', /^#{1,6}\s+(?:\d+(?:\.\d+)*\s+)?вывод(?:ы|ов)?(?:\s|:|$)/i],
    ];
    const foundSections = reqSections.filter(([, re]) => content.split('\n').some(l => re.test(l.trim())));
    if (foundSections.length > 0) {
      for (const [name, re] of reqSections) {
        if (!content.split('\n').some(l => re.test(l.trim()))) {
          warnings.push(`В отчете есть разделы, но отсутствует обязательный раздел «${name}».`);
        }
      }
    }

    const totalWords = content.split(/\s+/).filter(Boolean).length
      + (meta.references || []).reduce((sum, ref) => sum + formatReference(ref).split(/\s+/).filter(Boolean).length, 0);
    // Volume constants mirror backend linter.py. Single-cell listing tables
    // also contribute 0.3 pages, matching backend len(doc.tables).
    const WORDS_PER_PAGE = 220;
    const PAGES_PER_FIGURE = 0.4;
    const PAGES_PER_TABLE = 0.3;
    const estPages = Math.max(1, 1 + Math.round(totalWords / WORDS_PER_PAGE + figuresCount * PAGES_PER_FIGURE + (tableBlocks + listingsCount) * PAGES_PER_TABLE));

    const rawScore = 100 - (errors.length * 15) - (warnings.length * 4);
    const score = Math.max(0, Math.min(100, rawScore));

    return {
      score,
      isValid: errors.length === 0,
      errors,
      warnings,
      metrics: {
        margins: { left: 30, right: 15, top: 20, bottom: 20 },
        estPages,
        figuresCount,
        tablesCount: tableBlocks,
        listingsCount,
      }
    };
  }, [content, meta.references, images]);

  // Image lookup map.
  const [imageMap, setImageMap] = useState<Record<string, string>>({});
  const [imageSizes, setImageSizes] = useState<Record<string, { width: number; height: number }>>({});

  useEffect(() => {
    const urls: string[] = [];
    const map: Record<string, string> = {};
    const sizes: Record<string, { width: number; height: number }> = {};
    let active = true;

    images.forEach(img => {
      try {
        const url = URL.createObjectURL(img);
        urls.push(url);
        map[img.name] = url;
        map[img.name.toLowerCase()] = url;
      } catch {}
    });

    setImageMap(map);
    Promise.all(images.map(file => new Promise<void>(resolve => {
      const picture = new window.Image();
      picture.onload = () => {
        sizes[file.name] = { width: picture.naturalWidth, height: picture.naturalHeight };
        resolve();
      };
      picture.onerror = () => resolve();
      picture.src = map[file.name];
    }))).then(() => { if (active) setImageSizes(sizes); });

    return () => {
      active = false;
      urls.forEach(url => {
        try {
          URL.revokeObjectURL(url);
        } catch {}
      });
    };
  }, [images]);

  // Parse Markdown into preview blocks with estimated rendered heights.
  const parsedBlocks = useMemo(() => {
    const lines = content.split('\n');
    const blocks: ParsedBlock[] = [];
    let i = 0;
    // Match backend numbering: preserve author numbers verbatim, including
    // compound numbers, and use the next free number only as a fallback.
    const usedFigNums = new Set<string>();
    const figAuto = { value: 0 };
    const usedTblNums = new Set<string>();
    const tblAuto = { value: 0 };
    let lstCounter = 0;
    let lastHeading = '';

    while (i < lines.length) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        i++;
        continue;
      }

      // Support all six Markdown heading levels.
      const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
      if (headingMatch) {
        const level = headingMatch[1].length;
        const title = headingMatch[2].replace(/\.+$/, '');
        lastHeading = title;
        blocks.push({
          id: `h-${blocks.length}`,
          type: `h${level}` as ParsedBlock['type'],
          data: { title },
          estHeight: level === 1 ? 40 : level === 2 ? 38 : 34
        });
        i++;
        continue;
      }

      // Display equations with optional external numbering.
      if (trimmed.startsWith('$$')) {
        let rawFormula = '';
        let eqNum: string | undefined;

        // Single-line display equation.
        const singleMatch = trimmed.match(/^\$\$(.*?)\$\$\s*(\((?:\d+(?:\.\d+)*|[а-яёА-ЯЁa-zA-Z0-9.\-]+)\))?$/);
        if (singleMatch) {
          rawFormula = singleMatch[1].trim();
          if (singleMatch[2]) {
            eqNum = singleMatch[2].trim();
          }
          i++;
        } else {
          // Multiline display equation.
          const formulaLines: string[] = [trimmed.slice(2)];
          i++;
          while (i < lines.length) {
            const cur = lines[i].trim();
            const closeMatch = cur.match(/\$\$\s*(\((?:\d+(?:\.\d+)*|[а-яёА-ЯЁa-zA-Z0-9.\-]+)\))?$/);
            if (closeMatch) {
              const beforeClose = cur.slice(0, closeMatch.index);
              if (beforeClose) formulaLines.push(beforeClose);
              if (closeMatch[1]) {
                eqNum = closeMatch[1].trim();
              }
              i++;
              break;
            } else {
              formulaLines.push(lines[i]);
              i++;
            }
          }
          rawFormula = formulaLines.join('\n').trim();
        }

        // Extract an internal tag or spaced number if no external number was found.
        let cleanFormula = rawFormula;
        if (!eqNum) {
          const tagMatch = cleanFormula.match(/\\tag\{([^}]+)\}/);
          if (tagMatch) {
            eqNum = tagMatch[1].startsWith('(') ? tagMatch[1] : `(${tagMatch[1]})`;
            cleanFormula = cleanFormula.replace(/\\tag\{[^}]+\}/, '').trim();
          } else {
            const quadMatch = cleanFormula.match(/(?:\\qquad|\\quad|\s{3,})\s*(\((?:\d+(?:\.\d+)*)\))\s*$/);
            if (quadMatch) {
              eqNum = quadMatch[1];
              cleanFormula = cleanFormula.slice(0, quadMatch.index).trim();
            }
          }
        }

        blocks.push({
          id: `math-${blocks.length}`,
          type: 'math',
          data: { formula: cleanFormula, eqNum },
          estHeight: 36
        });
        continue;
      }

       // Backtick and tilde code fences.
       const fenceMatch = trimmed.match(/^(`{3,}|~{3,})(.*)$/);
       if (fenceMatch) {
         const fence = fenceMatch[1];
         const fenceChar = fence[0];
         const rawInfo = fenceMatch[2].trim();
         const codeLines: string[] = [];
         i++;
         while (i < lines.length) {
           const closing = lines[i].trim();
           if (closing.startsWith(fenceChar.repeat(fence.length))
             && closing.slice(fence.length).trim() === '') break;
           codeLines.push(lines[i]);
           i++;
         }
         if (i < lines.length) {
           i++;
        }
        // Empty fences create neither a listing nor a table, matching markdown_parser.py.
        if (!codeLines.join('\n').trim()) {
          continue;
        }
        lstCounter++;
        const caption = cleanListingCaption(rawInfo, lstCounter);
        const lang = rawInfo.split(/\s+/)[0] || '';
        const code = codeLines.join('\n');
        const estHeight = 28 + codeLines.length * 15;
        blocks.push({
          id: `code-${blocks.length}`,
          type: 'code',
          data: { code, lang, caption, codeLines },
          estHeight
        });
        continue;
      }

      // Split paragraphs into text and image segments without losing surrounding
      // prose, matching the backend.
      const imagePattern = /!\[([^\]]*)\]\((<[^>]*>|[^)\s]+)(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\)/g;
      if (line.includes('![') && imagePattern.test(line)) {
        imagePattern.lastIndex = 0;
        const emitImage = (altRaw: string, srcRaw: string) => {
          const stripped = (altRaw || '').replace(/\.+$/, '').trim();
          const figNum = assignCaptionNumber(usedFigNums, figAuto, extractExplicitNumber(stripped, FIGURE_NUM_RE));
          // Use the backend's generic illustration title for empty alt text.
          const rawAlt = stripped || `Иллюстрация\u00A0${figNum}`;
          // Strip existing figure prefixes to avoid duplicate caption numbering,
          // matching backend clean_figure_caption (typography.py).
          // Use separator lookahead because JS word boundaries exclude Cyrillic.
          const cleanAlt = rawAlt.replace(/^(рисунок|рис)(?=[\s.\d:–—-]|$)\.?\s*\d*(?:\.\d+)*\s*[-–—:.]?\s*/i, '').trim() || rawAlt;
          const alt = capitalizeCaption(cleanAlt.replace(/\s+[-–—]\s+/g, ' — '));
          const filename = (srcRaw || '').trim().replace(/^<|>$/g, '');
          const layoutName = resolveImageName(filename, Object.keys(meta.image_layouts || {}));
          const layout = layoutName ? meta.image_layouts?.[layoutName] : undefined;
          const widthPx = (layout?.width_percent ?? (155 / 165) * 100) / 100 * (165 / 210 * 595);
          const maxHeightPx = (layout?.max_height_mm ?? 200) / 210 * 595;
          const dimensionsName = resolveImageName(filename, Object.keys(imageSizes));
          const dimensions = dimensionsName ? imageSizes[dimensionsName] : undefined;
          const renderWidthPx = dimensions?.height
            ? Math.min(widthPx, maxHeightPx * dimensions.width / dimensions.height)
            : widthPx;
          const pictureHeight = dimensions?.width
            ? renderWidthPx * dimensions.height / dimensions.width
            : 175;
          const caption = `Рисунок\u00A0${figNum} — ${alt}`;
          blocks.push({
            id: `img-${blocks.length}`,
            type: 'image',
            data: { alt, filename, caption, layout, widthPx: renderWidthPx, maxHeightPx },
            estHeight: Math.ceil(pictureHeight + (meta.hide_captions ? 18 : 44))
          });
        };
        const emitPara = (text: string) => {
          const t = text.trim();
          if (!t) return;
          const data = createPreviewParagraph(t);
          blocks.push({
            id: `p-${blocks.length}`,
            type: 'p',
            data,
            estHeight: data.linesEst * 21
          });
        };
        // A standalone image needs no text segmentation.
        if (trimmed.startsWith('![')) {
          const onlyImg = trimmed.match(/^!\[([^\]]*)\]\((<[^>]*>|[^)\s]+)(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\)$/);
          if (onlyImg) {
            emitImage(onlyImg[1], onlyImg[2]);
            i++;
            continue;
          }
        }
        const imgRe = imagePattern;
        let lastIdx = 0;
        let mImg: RegExpExecArray | null;
        let emitted = false;
        while ((mImg = imgRe.exec(line)) !== null) {
          emitPara(line.slice(lastIdx, mImg.index));
          emitImage(mImg[1], mImg[2]);
          lastIdx = mImg.index + mImg[0].length;
          emitted = true;
        }
        if (emitted) {
          emitPara(line.slice(lastIdx));
          i++;
          continue;
        }
      }

      // Accept Markdown tables with an optional trailing pipe, as markdown-it does.
      // Consume a preceding explicit table caption, matching the backend.
      if (trimmed.startsWith('|')) {
        const tableLines: string[] = [];
        while (i < lines.length && lines[i].trim().startsWith('|')) {
          tableLines.push(lines[i].trim());
          i++;
        }
        const isSepRow = (r: string) => {
          const cells = r.split('|').map(c => c.trim()).filter(Boolean);
          return cells.length > 0 && cells.every(c => /^:?-+:?$/.test(c));
        };
        const dataRows = tableLines.filter(r => !isSepRow(r));
        let tableTitle = 'Исходные данные и параметры';
        let explicitTbl: string | null = null;
        const prev = blocks[blocks.length - 1];
        if (prev && prev.type === 'p') {
          const pt = String(prev.data.text || '');
          const mCap = pt.match(/^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)\s*[:–—.\-]\s*([\s\S]*)$/i)
            || (pt.length < 80 ? pt.match(/^(?:таблица|табл\.?)\s*(\d+(?:\.\d+)*)\b\s*([\s\S]*)$/i) : null);
          if (mCap) {
            explicitTbl = mCap[1];
            const cand = (mCap[2] || '').trim();
            if (cand) tableTitle = cand.charAt(0).toUpperCase() + cand.slice(1);
            blocks.pop();
          }
        }
        if (explicitTbl === null && tableTitle === 'Исходные данные и параметры' && lastHeading && /таблиц/i.test(lastHeading)) {
          const clean = lastHeading.replace(/^(\d+\.?\s*)?(таблица|табл\.?)\s*\d*(?:\.\d+)*\s*[:–—.-]?\s*/i, '').trim();
          if (clean) tableTitle = clean.charAt(0).toUpperCase() + clean.slice(1);
          explicitTbl = extractExplicitNumber(lastHeading, TABLE_NUM_RE);
        }
        const tblNum = assignCaptionNumber(usedTblNums, tblAuto, explicitTbl);
        const caption = `Таблица\u00A0${tblNum} — ${tableTitle}`;
        const estHeight = estimateTableHeight(dataRows, caption, meta.hide_captions);
        blocks.push({
          id: `tbl-${blocks.length}`,
          type: 'table',
          data: { dataRows, caption },
          estHeight
        });
        continue;
      }

      // GOST lists preserve author start numbers, matching the backend.
      // Indentation represents nesting; bullet levels use en dashes.
      if (/^(\d+[.)]|-|\*|–|—)\s/.test(trimmed)) {
        const isCurrentOrdered = /^\d+[.)]\s/.test(trimmed);
        const listItems: { text: string; depth: number; estHeight: number }[] = [];
        let listStart = 1;
        const mStart = trimmed.match(/^(\d+)[.)]/);
        if (mStart) listStart = Math.max(1, parseInt(mStart[1], 10) || 1);

        while (i < lines.length) {
          const rawLine = lines[i];
          const tr = rawLine.trim();
          if (!tr) {
            // Skip a blank line when the next item uses the same list type.
            if (i + 1 < lines.length && (isCurrentOrdered ? /^\d+[.)]\s/ : /^[-*–—]\s/).test(lines[i + 1].trim())) {
              i++;
              continue;
            }
            break;
          }

          const isItemOrdered = /^\d+[.)]\s/.test(tr);
          const isItemBullet = /^[-*–—]\s/.test(tr);

          // Switching between ordered and bullet items ends the current list.
          if (listItems.length > 0 && isCurrentOrdered !== isItemOrdered) {
            break;
          }

          if (isItemOrdered || isItemBullet) {
            const rawWithSpaces = rawLine.replace(/\t/g, '  ');
            const indent = rawWithSpaces.match(/^ */)?.[0].length || 0;
            const cleanContent = tr.replace(/^(\d+[.)]|-|\*|–|—)\s*/, '');
            // Estimate ~65 characters per line at 14 pt within a 467 px text area.
            const linesEst = Math.max(1, Math.ceil((cleanContent.length + 10) / 65));
            const itHeight = linesEst * 21;
            listItems.push({ text: tr, depth: indent >= 2 ? 1 : 0, estHeight: itHeight });
            i++;
          } else if (listItems.length > 0 && (rawLine.startsWith('  ') || rawLine.startsWith('\t') || !/^[#|`$]/.test(tr))) {
            // Continue a multiline list item.
            const lastItem = listItems[listItems.length - 1];
            lastItem.text += ' ' + tr;
            const cleanContent = lastItem.text.replace(/^(\d+[.)]|-|\*|–|—)\s*/, '');
            const linesEst = Math.max(1, Math.ceil((cleanContent.length + 10) / 65));
            lastItem.estHeight = linesEst * 21;
            i++;
          } else {
            break;
          }
        }

        const totalListHeight = listItems.reduce((acc, it) => acc + it.estHeight, 0);
        blocks.push({
          id: `list-${blocks.length}`,
          type: 'list',
          data: { items: listItems, start: listStart },
          estHeight: totalListHeight
        });
        continue;
      }

      // Ordinary prose paragraphs.
      const paraLines: string[] = [];
      while (
        i < lines.length &&
        lines[i].trim() &&
        !lines[i].trim().startsWith('#') &&
        !lines[i].trim().startsWith('$$') &&
         !/^(`{3,}|~{3,})/.test(lines[i].trim()) &&
        !lines[i].trim().startsWith('![') &&
        !lines[i].trim().startsWith('|') &&
        !/^(\d+[.)]|-|\*|–|—)\s/.test(lines[i].trim())
      ) {
        paraLines.push(lines[i].trim());
        i++;
      }
      const text = paraLines.join(' ');
      const data = createPreviewParagraph(text);
      const estHeight = data.linesEst * 21;
      blocks.push({
        id: `p-${blocks.length}`,
        type: 'p',
        data,
        estHeight
      });
    }

    return blocks;
  }, [content, meta.image_layouts, meta.hide_captions, imageSizes]);

  // Paginate bibliography entries as atomic blocks, using the same
  // 68-character lines and 21 px line height as prose.
  const bibBlocks: ParsedBlock[] = useMemo(() => {
    const refs = meta.references || [];
    if (refs.length === 0 || !content.trim()) return [];
    const blocks: ParsedBlock[] = [{
      id: 'bib-head', type: 'bibhead', data: {}, estHeight: 34
    }];
    refs.forEach((ref, rIdx) => {
      const text = `${rIdx + 1}.\u00A0${formatReference(ref)}`;
      const linesEst = Math.max(1, Math.ceil(text.length / 68));
      blocks.push({ id: `bib-${rIdx}`, type: 'bibref', data: { text }, estHeight: linesEst * 21 });
    });
    return blocks;
  }, [meta.references, content]);

  // Approximate the DOCX layout by distributing blocks across A4 pages.
  const parsedPages = useMemo(() => paginatePreviewBlocks(
    [...parsedBlocks, ...bibBlocks], pageBreakBeforeH1
  ), [parsedBlocks, bibBlocks, pageBreakBeforeH1]);

  // Compute dynamic title-page spacing to mirror title_page.py.
  const titleGaps = useMemo(() => {
    const numTeachers = meta.teachers?.length ?? 1;
    const numStudents = meta.students?.length ?? 1;
    const numPersons = numTeachers + numStudents;
    const themeLines = Math.max(1, Math.floor(((meta.work_theme || '').length + 35) / 45));
    const hasDetails = Boolean(meta.institute || meta.department);
    const headerDxa = normalizeLogoMode(meta.logo_mode) === 'none'
      ? (hasDetails ? 1500 : 1050) : (hasDetails ? 1710 : 1110);
    const fixedDxa = headerDxa + 1180 + themeLines * 300 + numPersons * 750 + 240;
    const targetDxa = 14250 - Math.max(0, numPersons - 2) * 150 - Math.max(0, themeLines - 1) * 120;
    const available = Math.max(0, targetDxa - fixedDxa);
    const gap1 = available > 1000 ? Math.floor(available * 0.30) : available > 0 ? Math.max(100, Math.floor(available * 0.30)) : 40;
    const gap2 = available > 1000 ? Math.floor(available * 0.32) : available > 0 ? Math.max(100, Math.floor(available * 0.32)) : 40;
    return { gap1Px: gap1 / 20, gap2Px: gap2 / 20 };
  }, [meta.teachers, meta.students, meta.work_theme, meta.logo_mode, meta.institute, meta.department]);

  const ministryLines = useMemo(() => {
    let text = meta.ministry || 'МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ\nРОССИЙСКОЙ ФЕДЕРАЦИИ';
    if (!text.includes('\n')) {
      if (text.includes('РОССИЙСКОЙ ФЕДЕРАЦИИ')) {
        text = text.replace('РОССИЙСКОЙ ФЕДЕРАЦИИ', '\nРОССИЙСКОЙ ФЕДЕРАЦИИ').trim();
      } else if (text.length > 45) {
        const words = text.trim().split(/\s+/);
        const middle = Math.floor(words.length / 2);
        text = `${words.slice(0, middle).join(' ')}\n${words.slice(middle).join(' ')}`;
      }
    }
    return text.split('\n');
  }, [meta.ministry]);

  // Compute the unscaled document height for scrolling.
  const totalPagesCount = 1 + parsedPages.length;
  const pageHeight = 842;
  const pageGap = 32; // space-y-8 = 32px
  const totalUnscaledHeight = totalPagesCount * pageHeight + Math.max(0, totalPagesCount - 1) * pageGap;

  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden h-full">
      {/* A4/compliance tabs, zoom, and formatting controls. */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-200 bg-slate-50 px-2.5 sm:px-4 py-2 gap-2 shrink-0">
        <div className="flex items-center gap-1.5 sm:gap-2">
          <button
            onClick={() => setActiveTab('preview')}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 sm:px-3 py-1.5 text-xs font-bold transition-all ${
              activeTab === 'preview'
                ? 'bg-white text-blue-700 shadow-sm border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Eye className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Макет А4</span>
            <span className="sm:hidden">А4</span>
          </button>
          <button
            onClick={() => setActiveTab('linter')}
            className={`flex items-center gap-1.5 rounded-lg px-2.5 sm:px-3 py-1.5 text-xs font-bold transition-all ${
              activeTab === 'linter'
                ? 'bg-white text-blue-700 shadow-sm border border-slate-200'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <ShieldCheck className="h-3.5 w-3.5" />
            <span className="hidden sm:inline">Нормоконтроль</span>
            <span className="sm:hidden">ГОСТ</span>
            <span
              className={`rounded-full px-1.5 py-0.5 text-[10px] font-extrabold ${
                !hasReportText
                  ? 'bg-slate-100 text-slate-600'
                  : linterStatus.score >= 90
                  ? 'bg-emerald-100 text-emerald-800'
                  : linterStatus.score >= 70
                  ? 'bg-amber-100 text-amber-800'
                  : 'bg-red-100 text-red-800'
              }`}
              title={hasReportText ? undefined : 'Нет текста для проверки'}
            >
              {hasReportText ? `${linterStatus.score}/100` : 'Нет текста'}
            </span>
          </button>
        </div>

        {/* Zoom controls and layout settings. */}
        <div className="flex items-center gap-2">
          {/* Zoom controller. */}
          {activeTab === 'preview' && (
            <div className="flex items-center bg-slate-200/80 p-0.5 rounded-lg text-xs">
              <button
                type="button"
                onClick={() => handleZoomChange(-0.1)}
                disabled={zoom <= 0.4}
                className="p-1 rounded hover:bg-white text-slate-700 disabled:opacity-40 transition-all"
                title="Уменьшить масштаб (–10%)"
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={resetZoom}
                className="px-1.5 py-0.5 text-[11px] font-bold text-slate-700 hover:text-blue-700"
                title="Сбросить масштаб на 100%"
              >
                {Math.round(zoom * 100)}%
              </button>
              <button
                type="button"
                onClick={() => handleZoomChange(0.1)}
                disabled={zoom >= 2.0}
                className="p-1 rounded hover:bg-white text-slate-700 disabled:opacity-40 transition-all"
                title="Увеличить масштаб (+10%)"
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </button>
              <button
                type="button"
                onClick={toggleFitWidth}
                className={`p-1 rounded text-[11px] font-semibold transition-all ${
                  isFitWidth ? 'bg-blue-600 text-white shadow-sm' : 'hover:bg-white text-slate-700'
                }`}
                title={isFitWidth ? "Отключить подгонку по ширине" : "Подогнать масштаб по ширине окна"}
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </button>
            </div>
          )}

          {/* Formatting settings dropdown. */}
          <div className="relative" ref={settingsRef}>
            <button
              type="button"
              onClick={() => setIsSettingsOpen(!isSettingsOpen)}
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold transition-all ${
                isSettingsOpen
                  ? 'bg-blue-50 border-blue-300 text-blue-700 shadow-sm'
                  : 'bg-white border-slate-300 text-slate-700 hover:bg-slate-50'
              }`}
              title="Настройки оформления и верстки документа по ГОСТ 7.32"
            >
              <SlidersHorizontal className="h-3.5 w-3.5 text-slate-500" />
              <span>Оформление</span>
              <ChevronDown className={`h-3 w-3 transition-transform ${isSettingsOpen ? 'rotate-180' : ''}`} />
            </button>

            {isSettingsOpen && (
              <div className="absolute right-0 top-full mt-1.5 w-72 max-w-[calc(100vw-24px)] max-h-[70vh] overflow-y-auto rounded-xl bg-white border border-slate-200 shadow-xl p-3 z-50 text-xs space-y-3">
                <div className="font-bold text-slate-800 border-b border-slate-100 pb-1.5 flex items-center justify-between">
                  <span>Параметры верстки</span>
                  <span className="text-[10px] text-slate-400 font-normal">ГОСТ 7.32 / СТО</span>
                </div>

                {/* Heading alignment. */}
                {onHeadingAlignmentChange && (
                  <div>
                    <div className="text-[11px] font-semibold text-slate-600 mb-1">Выравнивание разделов:</div>
                    <div className="grid grid-cols-2 gap-1 bg-slate-100 p-0.5 rounded-lg">
                      <button
                        type="button"
                        onClick={() => onHeadingAlignmentChange('center')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          headingAlignment !== 'left' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="Полужирные заголовки разделов по центру — ГОСТ 7.32-2017 (по умолчанию)"
                      >
                        По центру
                      </button>
                      <button
                        type="button"
                        onClick={() => onHeadingAlignmentChange('left')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          headingAlignment === 'left' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="С абзацного отступа — вариант отдельных методичек кафедр"
                      >
                        Слева
                      </button>
                    </div>
                  </div>
                )}

                {/* Section page breaks. */}
                {onPageBreakBeforeH1Change && (
                  <label className="flex items-center justify-between cursor-pointer select-none pt-1">
                    <span className="text-[11px] font-medium text-slate-700">Разделы с новой страницы</span>
                    <input
                      type="checkbox"
                      checked={pageBreakBeforeH1}
                      onChange={e => onPageBreakBeforeH1Change(e.target.checked)}
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                  </label>
                )}

                {/* Page numbering. */}
                {onPageNumberingChange && (
                  <div className="pt-1">
                    <div className="text-[11px] font-semibold text-slate-600 mb-1">Нумерация страниц:</div>
                    <div className="grid grid-cols-3 gap-1 bg-slate-100 p-0.5 rounded-lg">
                      <button
                        type="button"
                        onClick={() => onPageNumberingChange('center')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          pageNumbering === 'center' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="По центру внизу (ГОСТ 7.32)"
                      >
                        По центру
                      </button>
                      <button
                        type="button"
                        onClick={() => onPageNumberingChange('right')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          pageNumbering === 'right' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="Справа внизу (ГОСТ 2.105)"
                      >
                        Справа
                      </button>
                      <button
                        type="button"
                        onClick={() => onPageNumberingChange('none')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          pageNumbering === 'none' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="Без номеров"
                      >
                        Откл.
                      </button>
                    </div>
                  </div>
                )}

                {/* Figure and listing caption visibility. */}
                {onHideCaptionsChange && (
                  <label className="flex items-center justify-between cursor-pointer select-none pt-1 border-t border-slate-100">
                    <span className="text-[11px] font-medium text-slate-700">Скрыть подписи к рисункам и листингам</span>
                    <input
                      type="checkbox"
                      checked={Boolean(meta.hide_captions)}
                      onChange={e => onHideCaptionsChange(e.target.checked)}
                      className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                  </label>
                )}

                {/* DOCX equation mode. */}
                {onLatexModeChange && (
                  <div className="pt-1 border-t border-slate-100">
                    <div className="text-[11px] font-semibold text-slate-600 mb-1">Формулы LaTeX в DOCX:</div>
                    <div className="grid grid-cols-2 gap-1 bg-slate-100 p-0.5 rounded-lg">
                      <button
                        type="button"
                        onClick={() => onLatexModeChange('omml')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          latexMode !== 'unicode' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="Формульные объекты Word (OMML)"
                      >
                        Нативные
                      </button>
                      <button
                        type="button"
                        onClick={() => onLatexModeChange('unicode')}
                        className={`py-1 text-center font-medium rounded text-[11px] transition-all ${
                          latexMode === 'unicode' ? 'bg-white text-blue-700 shadow-sm font-bold' : 'text-slate-600 hover:text-slate-900'
                        }`}
                        title="Обычный текст без формульных объектов Word"
                      >
                        Упрощённые
                      </button>
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1 leading-snug">
                      Упрощённые — обычный текст без объектов Word.
                    </p>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="text-[11px] text-slate-500 font-semibold hidden sm:block">
            {totalPagesCount} стр.
          </div>
        </div>
      </div>

      {/* Center children with block layout and mx-auto. Flex justify-center
          would clip the left edge on horizontal overflow beyond scroll reach. */}
      <div
        ref={previewContainerRef}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-auto bg-slate-200/70 p-2 sm:p-4 md:p-6"
      >
        {activeTab === 'preview' ? (
          <div
            style={{
              width: `${Math.round(595 * zoom)}px`,
              minHeight: `${Math.round(totalUnscaledHeight * zoom)}px`,
              position: 'relative'
            }}
            className="mx-auto shrink-0 transition-all duration-75"
          >
            <div
              style={{
                transform: `scale(${zoom})`,
                transformOrigin: 'top left',
                width: '595px',
                position: 'absolute',
                top: 0,
                left: 0
              }}
              className="space-y-8 flex flex-col items-center select-text"
            >
            {/* ------------------------------------------------------------- */}
            {/* GOST title page: 210×297 mm; margins L30/R15/T20/B20 mm. */}
            {/* ------------------------------------------------------------- */}
            <div
              className="w-[595px] h-[842px] bg-white rounded shadow-[0_4px_25px_rgba(0,0,0,0.14)] text-black relative flex flex-col justify-between overflow-hidden shrink-0 select-text"
              style={{
                fontFamily: '"Times New Roman", Times, "Liberation Serif", serif',
                paddingTop: '57px',
                paddingBottom: '57px',
                paddingLeft: '85px',
                paddingRight: '43px'
              }}
            >
              <div className="flex-1 flex flex-col h-full">
                {/* Centered header with an optional left logo, matching title_page.py. */}
                <div className="relative w-full min-h-[85px]">
                  {/* Floating logo when enabled. */}
                  {normalizeLogoMode(meta.logo_mode) !== 'none' && (
                    <div className="absolute left-[-73px] top-[-23px] w-[145px] h-[78px] flex items-center justify-start">
                      <img
                        src={normalizeLogoMode(meta.logo_mode) === 'custom' && meta.custom_logo ? meta.custom_logo : "/default_logo.png"}
                        alt="Логотип"
                        className="h-full w-full object-contain"
                        onError={e => {
                          (e.target as HTMLElement).style.display = 'none';
                        }}
                      />
                    </div>
                  )}

                  {/* Ministry/university text reserves logo space or spans the full width. */}
                  <div className={`${normalizeLogoMode(meta.logo_mode) !== 'none' ? 'pl-[64px]' : 'w-full'} text-center text-black leading-[1.15]`}>
                    <p className="font-normal text-[12px]">
                      {ministryLines.map((line, i) => (
                        <React.Fragment key={i}>
                          {i > 0 && <br />}
                          {line}
                        </React.Fragment>
                      ))}
                    </p>
                    <p className={`font-normal text-[12px] whitespace-pre-line ${normalizeLogoMode(meta.logo_mode) !== 'none' ? '' : 'mt-1'}`}>
                      {meta.university || 'НАИМЕНОВАНИЕ УНИВЕРСИТЕТА'}
                    </p>
                    {meta.institute && (
                      <p className="text-[12px] mt-1.5 font-normal whitespace-pre-line">
                        {meta.institute}
                      </p>
                    )}
                    {meta.department && (
                      <p className="text-[12px] font-normal whitespace-pre-line">
                        Кафедра «{meta.department.replace(/^(кафедра|кафедры)\s*/i, '').trim().replace(/^["«]+|["»]+$/g, '')}»
                      </p>
                    )}
                  </div>
                </div>

                {/* Report heading with dynamic gap1Px spacing. */}
                <div className="text-center space-y-1.5" style={{ marginTop: `${titleGaps.gap1Px}px` }}>
                  <h2 className="text-[18px] font-bold">
                    {meta.doc_type || 'ОТЧЕТ'}
                  </h2>
                  <p className="text-[13px] font-normal">
                    {meta.work_type || 'о выполнении лабораторной работы'}{meta.work_number && meta.work_number > 0 ? ` №${meta.work_number}` : ''}
                  </p>
                  <p className="text-[14px] font-bold">
                    «{(meta.work_theme || 'ТЕМА РАБОТЫ').replace(/^«|»$/g, '')}»
                  </p>
                  <p className="text-[13px] font-normal">
                    по дисциплине «{(meta.discipline || 'НАИМЕНОВАНИЕ ДИСЦИПЛИНЫ').replace(/^«|»$/g, '')}»
                  </p>
                </div>

                {/* Signature table with dynamic gap2Px spacing and fixed column widths. */}
                <div className="text-[10px]" style={{ marginTop: `${titleGaps.gap2Px}px` }}>
                  <table className="w-full text-center border-collapse">
                    <tbody>
                      {(meta.teachers || []).map((t, idx) => {
                        const normalizedTeacherFio = normalizeFio(t.fio);
                        return (
                          <React.Fragment key={`t-${idx}`}>
                            <tr>
                              <td className="text-left font-bold w-[105px] align-bottom pb-0.5">
                                {idx === 0 ? ((meta.teachers?.length || 0) > 1 ? 'Преподаватели' : 'Преподаватель') : ''}
                              </td>
                              <td className="border-b border-black w-[85px] pb-0.5 align-bottom">
                                {t.role || 'ст. преп.'}
                              </td>
                              <td className="border-b border-black w-[85px] pb-0.5"></td>
                              <td className="border-b border-black w-[71px] pb-0.5"></td>
                              <td className="border-b border-black text-center pr-1 pb-0.5 align-bottom w-[122px]">
                                {normalizedTeacherFio}
                              </td>
                            </tr>
                            <tr className="text-[7.5px] text-black leading-none">
                              <td></td>
                              <td className="pt-0.5">(должность)</td>
                              <td className="pt-0.5">(подпись)</td>
                              <td className="pt-0.5">(дата)</td>
                              <td className="pt-0.5">(инициалы, фамилия)</td>
                            </tr>
                          </React.Fragment>
                        );
                      })}

                      {(meta.students || []).map((s, idx) => {
                        const normalizedStudentFio = normalizeFio(s.fio);
                        return (
                          <React.Fragment key={`s-${idx}`}>
                            <tr>
                              <td className="text-left font-bold w-[105px] pt-3.5 align-bottom pb-0.5">
                                {idx === 0 ? ((meta.students?.length || 0) > 1 ? 'Студенты' : 'Студент') : ''}
                              </td>
                              <td className="border-b border-black w-[85px] pt-3.5 pb-0.5 align-bottom">
                                {s.group || ''}
                              </td>
                              <td className="border-b border-black w-[85px] pt-3.5 pb-0.5"></td>
                              <td className="border-b border-black w-[71px] pt-3.5 pb-0.5"></td>
                              <td className="border-b border-black text-center pr-1 pt-3.5 pb-0.5 align-bottom w-[122px]">
                                {normalizedStudentFio}
                              </td>
                            </tr>
                            <tr className="text-[7.5px] text-black leading-none">
                              <td></td>
                              <td className="pt-0.5">(группа)</td>
                              <td className="pt-0.5">(подпись)</td>
                              <td className="pt-0.5">(дата)</td>
                              <td className="pt-0.5">(инициалы, фамилия)</td>
                            </tr>
                          </React.Fragment>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                {/* City/year footer centered just above the bottom margin. */}
                <div className="text-center text-[12px] font-serif mt-auto pt-4 pb-0">
                  <p>{meta.city ? `${meta.city} ` : ''}{meta.year || new Date().getFullYear()}</p>
                </div>
              </div>

              {/* Hide the first page number under GOST. */}
              <div className="absolute bottom-2 right-4 text-[9px] text-slate-400 font-sans select-none">
                (Стр. 1 скрыта по ГОСТ)
              </div>
            </div>

            {/* ------------------------------------------------------------- */}
            {/* Report body pages approximate the DOCX layout. */}
            {/* ------------------------------------------------------------- */}
            {parsedPages.map((pageBlocks, pIdx) => {
              const pageNumber = pIdx + 2;
              return (
                <div
                  key={pageNumber}
                  className="w-[595px] h-[842px] bg-white rounded shadow-[0_4px_25px_rgba(0,0,0,0.14)] text-black relative flex flex-col justify-between overflow-hidden shrink-0 select-text"
                  style={{
                    fontFamily: '"Times New Roman", Times, "Liberation Serif", serif',
                    paddingTop: '57px',
                    paddingBottom: '57px',
                    paddingLeft: '85px',
                    paddingRight: '43px'
                  }}
                >
                  {/* Justified body text in Times New Roman 14 pt with 1.5 spacing. */}
                  <div 
                    lang="ru"
                    className="flex-1 flex flex-col justify-start text-[14px] leading-[1.5] text-black select-text"
                    style={{ hyphens: 'auto' }}
                  >
                    {pageBlocks.map(block => {
                      // H1: bold 14 pt, without a trailing period.
                      if (block.type === 'h1') {
                        return (
                          <h2
                            key={block.id}
                            className={`text-[14px] font-bold pt-3 pb-1.5 leading-snug select-text ${
                              headingAlignment === 'center' ? 'text-center' : 'text-left'
                            }`}
                            style={{ textIndent: '0px' }}
                          >
                            {block.data.title}
                          </h2>
                        );
                      }

                      // H2: bold 14 pt with a 1.25 cm first-line indent.
                      if (block.type === 'h2') {
                        return (
                          <h3
                            key={block.id}
                            className="text-[14px] font-bold pt-2.5 pb-1 leading-snug text-left select-text"
                            style={{ textIndent: '35.4px' }}
                          >
                            {block.data.title}
                          </h3>
                        );
                      }

                      // H3: bold 13 pt with a first-line indent.
                      if (block.type === 'h3') {
                        return (
                          <h4
                            key={block.id}
                            className="text-[13px] font-bold pt-2 pb-0.5 leading-snug text-left select-text"
                            style={{ textIndent: '35.4px' }}
                          >
                            {block.data.title}
                          </h4>
                        );
                      }

                      if (block.type === 'h4' || block.type === 'h5' || block.type === 'h6') {
                        return (
                          <h5
                            key={block.id}
                            className="text-[12px] font-bold pt-1.5 pb-0.5 leading-snug text-left select-text"
                            style={{ textIndent: '35.4px' }}
                          >
                            {block.data.title}
                          </h5>
                        );
                      }

                      // Listings use white backgrounds, thin borders, and Times New Roman 10 pt.
                      if (block.type === 'code') {
                        return (
                          <div key={block.id} className="pt-2 pb-2">
                            {!meta.hide_captions && (
                              <div 
                                className="text-[12px] italic mb-1 text-left font-serif leading-none"
                                style={{ textIndent: '0px' }}
                              >
                                {block.data.caption}
                              </div>
                            )}
                            <div className="p-2.5 font-serif text-[10px] leading-tight text-left overflow-x-auto text-black bg-white border border-black">
                              <pre className="whitespace-pre font-serif m-0">{block.data.code}</pre>
                            </div>
                          </div>
                        );
                      }

                      // Display equation.
                      if (block.type === 'math') {
                        return (
                          <div key={block.id} className="py-2 flex items-center justify-between font-serif text-[14px] text-black">
                            <div className="w-14 flex-shrink-0" />
                            <div className="flex-1 text-center overflow-x-auto">
                              {renderMathFormula(block.data.formula, latexMode, true)}
                            </div>
                            <div className="w-14 flex-shrink-0 text-right pr-1 select-none font-normal text-[14px]">
                              {block.data.eqNum || ''}
                            </div>
                          </div>
                        );
                      }

                      // Centered illustration with a 14 pt caption below.
                      if (block.type === 'image') {
                        const directUrl = resolveImagePreviewUrl(block.data.filename, imageMap, images);
                        const align = block.data.layout?.align || 'center';
                        return (
                          <div key={block.id} className="pt-2 pb-2">
                            {directUrl ? (
                              <img
                                src={directUrl}
                                alt={block.data.alt}
                                className="max-w-full object-contain my-1"
                                style={{
                                  width: `${block.data.widthPx}px`, maxHeight: `${block.data.maxHeightPx}px`,
                                  marginLeft: align === 'left' ? 0 : 'auto',
                                  marginRight: align === 'right' ? 0 : 'auto',
                                }}
                              />
                            ) : (
                              <div className="h-14 bg-slate-50 border border-dashed border-slate-300 rounded flex items-center justify-center text-[11px] text-slate-500 font-mono my-1">
                                [ Иллюстрация: {block.data.alt} ({block.data.filename}) ]
                              </div>
                            )}
                            {!meta.hide_captions && (
                               <p className="text-[14px] mt-1 mb-2 font-serif text-center font-normal leading-snug">
                                {block.data.caption}
                              </p>
                            )}
                          </div>
                        );
                      }

                      // Table: unindented left caption, thin GOST grid, bold header.
                      if (block.type === 'table') {
                        return (
                          <div key={block.id} className="pt-2.5 pb-2">
                            {!meta.hide_captions && (
                              <div 
                                className="text-[14px] mb-1 text-left font-serif font-normal leading-none"
                                style={{ textIndent: '0px' }}
                              >
                                {block.data.caption}
                              </div>
                            )}
                            <table className="w-full table-fixed text-left border-collapse border border-black text-[11px] leading-snug">
                              <tbody>
                                {block.data.dataRows.map((row: string, rI: number) => {
                                  const cells = splitPreviewTableRow(row);
                                  const isHeader = rI === 0;
                                  return (
                                    <tr key={rI} className={isHeader ? 'bg-white font-bold' : ''}>
                                      {cells.map((c: string, cI: number) => (
                                        <td
                                          key={cI}
                                          className={`p-1.5 border border-black [overflow-wrap:anywhere] ${
                                            isHeader ? 'text-center font-bold' : 'text-left'
                                          }`}
                                        >
                                          {renderFormattedText(c.trim(), latexMode)}
                                        </td>
                                      ))}
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>
                        );
                      }

                      // GOST lists use a 1.25 cm first-line indent and 1.5 spacing.
                      if (block.type === 'list') {
                        const startNum = Math.max(1, block.data.start || 1);
                        return (
                          <div key={block.id} className="my-0">
                            {block.data.items.map((it: string | { text: string; depth: number }, itemI: number) => {
                              const raw = typeof it === 'string' ? it : it.text;
                              const depth = typeof it === 'string' ? 0 : it.depth;
                              const trimmed = raw.trim();
                              const isOrd = /^\d+[.)]/.test(trimmed);
                              const matchDelim = trimmed.match(/^\d+([.)])/);
                              const delim = matchDelim ? matchDelim[1] : '.';
                              const cleanContent = trimmed.replace(/^(\d+[.)]|-|\*|–|—)\s*/, '');
                              const prefix = isOrd ? `${startNum + itemI}${delim}\u00A0` : '–\u00A0';
                              return (
                                <p 
                                  key={itemI} 
                                  className="leading-[1.5] text-justify m-0 p-0"
                                  style={{ textIndent: '35.4px', marginLeft: depth > 0 ? '18px' : '0px' }}
                                >
                                  <span className="select-none">{prefix}</span>
                                  <span>{renderFormattedText(cleanContent, latexMode)}</span>
                                </p>
                              );
                            })}
                          </div>
                        );
                      }

                      // Bibliography heading uses the bold 14 pt H1 style.
                      if (block.type === 'bibhead') {
                        return (
                          <h2
                            key={block.id}
                            className={`text-[14px] font-bold pt-3 pb-1.5 leading-snug select-text ${
                              headingAlignment === 'center' ? 'text-center' : 'text-left'
                            }`}
                            style={{ textIndent: '0px' }}
                          >
                            СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ
                          </h2>
                        );
                      }

                      // Bibliography entries use prose layout with preformatted text.
                      if (block.type === 'bibref') {
                        return (
                          <p
                            key={block.id}
                            className="leading-[1.5] m-0 p-0 text-justify text-[14px]"
                            style={{ textIndent: '35.4px' }}
                          >
                            {block.data.text}
                          </p>
                        );
                      }

                      // GOST 7.32 prose: Times New Roman 14 pt, 1.5 spacing,
                      // justified alignment, and a 1.25 cm first-line indent.
                      const isStandaloneCode = block.data.isStandaloneCode;

                      return (
                        <p 
                          key={block.id} 
                          className={`leading-[1.5] m-0 p-0 [overflow-wrap:anywhere] ${
                            isStandaloneCode ? 'text-center' : 'text-justify'
                          }`}
                          style={{ textIndent: (block.data.noIndent || block.data.continuation) ? '0px' : '35.4px' }}
                        >
                          {renderInlineParts(block.data.parts, latexMode)}
                        </p>
                      );
                    })}
                  </div>

                  {/* Footer with GOST page numbering. */}
                  {pageNumbering !== 'none' && (
                    <div
                      className={`text-[12px] font-serif text-black select-none pt-2 ${
                        pageNumbering === 'right' ? 'text-right' : 'text-center'
                      }`}
                    >
                      {pageNumber}
                    </div>
                  )}
                </div>
              );
            })}

            {/* Bibliography uses the shared bibhead/bibref pagination blocks. */}
            </div>
          </div>
        ) : !hasReportText ? (
          <p role="status" className="mx-auto w-full max-w-xl text-xs text-slate-600">Нет текста для проверки</p>
        ) : (
          /* GOST 7.32 compliance tab. */
          <div className="space-y-4 max-w-xl w-full mx-auto">
            {/* Score. */}
            <div className="rounded-xl border border-slate-200 bg-white p-4 sm:p-5 shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <span className="text-xs font-bold uppercase text-slate-500">
                  Оценка нормоконтроля
                </span>
                <div
                  className={`text-2xl sm:text-3xl font-black ${
                    linterStatus.score >= 90
                      ? 'text-emerald-600'
                      : linterStatus.score >= 70
                      ? 'text-amber-600'
                      : 'text-red-600'
                  }`}
                >
                  {linterStatus.score} / 100
                </div>
              </div>
              <div className="shrink-0">
                {linterStatus.isValid && linterStatus.warnings.length > 0 ? (
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-1.5 text-xs font-bold text-amber-900">Есть замечания</span>
                ) : linterStatus.isValid ? (
                  <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                    <CheckCircle className="h-4 w-4" /> Готово
                  </span>
                ) : (
                  <button
                    type="button"
                    onClick={onAutofix}
                    className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-bold bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm transition-colors"
                  >
                    <Wand2 className="h-3.5 w-3.5" /> Исправить автоматически
                  </button>
                )}
              </div>
            </div>

            {/* Layout metrics. */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div className="p-3 bg-white rounded-xl border border-slate-200">
                <span className="text-slate-500">Поля страницы ГОСТ:</span>
                <div className="font-bold text-slate-800 mt-1">
                  Л: 30 мм, П: 15 мм, В/Н: 20 мм
                </div>
                <div className="text-[10px] text-emerald-600 mt-0.5">Норма ГОСТ 7.32</div>
              </div>
              <div className="p-3 bg-white rounded-xl border border-slate-200">
                <span className="text-slate-500">Оценка объема:</span>
                <div className="font-bold text-slate-800 mt-1">
                  ~{linterStatus.metrics.estPages} стр. (А4)
                </div>
                <div className="text-[10px] text-slate-500 mt-0.5">
                  Иллюстраций: {linterStatus.metrics.figuresCount}, Таблиц: {linterStatus.metrics.tablesCount}, Листингов: {linterStatus.metrics.listingsCount}
                </div>
              </div>
            </div>

            {/* Errors. */}
            {linterStatus.errors.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-red-700">
                  Замечания ({linterStatus.errors.length}):
                </h4>
                {linterStatus.errors.map((err, i) => (
                  <div
                    key={i}
                    className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-800 flex items-start gap-2"
                  >
                    <XCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                    <span>{err}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Warnings. */}
            {linterStatus.warnings.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-amber-700">
                  Предупреждения ({linterStatus.warnings.length}):
                </h4>
                {linterStatus.warnings.map((warn, i) => (
                  <div
                    key={i}
                    className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800 flex items-start gap-2"
                  >
                    <span>{warn}</span>
                  </div>
                ))}
              </div>
            )}

            {linterStatus.errors.length === 0 && linterStatus.warnings.length === 0 && (
              <div className="rounded-lg bg-emerald-50 border border-emerald-200 p-4 text-xs text-emerald-800 flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-emerald-600 shrink-0" />
                <div>
                  <p className="font-bold">Замечаний нет</p>
                  <p className="text-emerald-700 mt-0.5">
                    Пустых строк, точек в заголовках и висячих ссылок нет.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
