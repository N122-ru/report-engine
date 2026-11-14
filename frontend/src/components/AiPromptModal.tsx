import React, { useState, useMemo, useEffect } from 'react';
import { 
  X, Copy, Check, Bot, 
  ClipboardCheck, Code, Layers
} from 'lucide-react';
import { ReportMetadata } from '../types';

interface AiPromptModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApplyImport: (cleanedMarkdown: string, extractedTheme?: string, mode?: 'replace' | 'append') => void;
  meta: ReportMetadata;
  onUpdateCustomInstructions?: (val: string) => void;
  onUpdatePromptLatex?: (val: boolean) => void;
  onUpdatePromptCodeBlocks?: (val: boolean) => void;
}

export const AiPromptModal: React.FC<AiPromptModalProps> = ({
  isOpen,
  onClose,
  onApplyImport,
  meta,
  onUpdateCustomInstructions,
  onUpdatePromptLatex,
  onUpdatePromptCodeBlocks
}) => {
  const [activeTab, setActiveTab] = useState<'prompts' | 'import'>('prompts');
  const [selectedPromptKey, setSelectedPromptKey] = useState<'vision' | 'code' | 'rewrite' | 'defense'>('vision');
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Custom instructions synchronized with metadata.
  const [customInstructions, setCustomInstructions] = useState<string>(meta.custom_instructions || '');

  // Request LaTeX equations or plain text without math delimiters/commands.
  // Initialize from the preset and synchronize changes in either direction.
  const [includeLatex, setIncludeLatex] = useState(meta.prompt_latex ?? true);

  const handleLatexChange = (val: boolean) => {
    setIncludeLatex(val);
    if (onUpdatePromptLatex) {
      onUpdatePromptLatex(val);
    }
  };

  // Fenced text/code is disabled by default in favor of prose, equations, and images.
  const [includeCodeBlocks, setIncludeCodeBlocks] = useState(
    meta.prompt_code_blocks ?? false
  );

  const handleCodeBlocksChange = (val: boolean) => {
    setIncludeCodeBlocks(val);
    if (onUpdatePromptCodeBlocks) {
      onUpdatePromptCodeBlocks(val);
    }
  };

  // AI response import state.
  const [rawAiText, setRawAiText] = useState('');

  useEffect(() => {
    setCustomInstructions(meta.custom_instructions || '');
  }, [meta.custom_instructions]);

  useEffect(() => {
    setIncludeCodeBlocks(meta.prompt_code_blocks ?? false);
  }, [meta.prompt_code_blocks]);

  const handleCustomInstructionsChange = (val: string) => {
    setCustomInstructions(val);
    if (onUpdateCustomInstructions) {
      onUpdateCustomInstructions(val);
    }
  };

  const copyToClipboard = async (text: string, key: string) => {
    // Fall back for insecure contexts and older browsers where
    // navigator.clipboard is unavailable or rejects writes.
    const fallbackCopy = () => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.opacity = '0';
      document.body.appendChild(ta);
      ta.select();
      let ok = false;
      try {
        ok = document.execCommand('copy');
      } catch {
        ok = false;
      }
      document.body.removeChild(ta);
      return ok;
    };

    let ok = false;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        ok = true;
      }
    } catch {
      ok = false;
    }
    if (!ok) {
      try {
        ok = fallbackCopy();
      } catch {
        ok = false;
      }
    }
    // Report success only after copying; otherwise explain manual copying.
    // The preformatted prompt already supports select-all.
    setCopiedKey(ok ? key : 'copy-error');
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const disciplineName = meta.discipline || 'Учебная дисциплина';
  const themeName = meta.work_theme || 'Тема работы';
  const labNum = meta.work_number || 1;
  const deptName = meta.department || '';

  const PROMPTS = useMemo(() => {
    const customSection = customInstructions.trim()
      ? `
---
Индивидуальные требования:
«««
${customInstructions.trim()}
»»»
Учитывай их, если они не требуют выдумывать данные и не нарушают формат Markdown.
---`
      : '';

    const narrativeRule = `• Пиши безлично: «выполнено», «настроено», «рассчитано», «получено». Не используй «я», «мы», «мной», «нами».`;

    const rawWorkType = (meta.work_type || 'о выполнении лабораторной работы').trim();
    const workAboutPhrase = /^по\s+/i.test(rawWorkType) || /^о\s+/i.test(rawWorkType)
      ? rawWorkType
      : `по ${rawWorkType}`;
    const numSuffix = meta.work_number ? ` №${meta.work_number}` : '';
    const workFullTitle = `${workAboutPhrase}${numSuffix}`;
    const isLabLikeWork = /лабораторн|практическ/i.test(rawWorkType);

    const structureInstruction = isLabLikeWork
      ? `Если методичка не задаёт другую структуру, используй:
# Цель работы
# Ход работы
# Вывод
Для курсовых, РГР, НИР, проектов и практик следуй методичке и исходному черновику; сохраняй обязательные разделы и не своди их содержание к «Ходу работы».`
      : `Следуй методичке, индивидуальным требованиям и исходному черновику. Сохраняй обязательные разделы этого вида работы; не своди теорию, задание, оборудование, исходные данные и библиографию к «Ходу работы».`;

    const univClause = meta.university ? ` (${meta.university})` : '';
    const deptClause = deptName ? ` по кафедре «${deptName}»` : '';
    const toneRole = `Ты составляешь отчёт ${workFullTitle}${deptClause}${univClause} по ГОСТ 7.32-2017.`;

    const mathRule = includeLatex
      ? `• Формулы и расчёты:
  - Не помещай их в таблицы и блоки кода.
  - Оформляй выкладки маркированным списком с LaTeX: $...$ или $$...$$.
  - После формулы с новой строки пиши «где $A$ — ...; $B$ — ...».
  - Используй только значения из материалов.`
      : `• Формулы и расчёты:
  - Не помещай их в таблицы и блоки кода.
  - Оформляй расчёты и переводы систем счисления маркированным списком обычного текста, например: - 10_10 = 00001010_2.`;

    const codeRule = includeCodeBlocks
      ? `• Код:
  - Короткие команды, имена функций и переменных пиши инлайн: \`...\`.
  - Многострочные блоки \`\`\`lang ... \`\`\` разрешены только для исходного кода, конфигураций и объёмных логов.`
      : `• Код:
  - Не используй многострочные блоки \`\`\`text, \`\`\`bash, \`\`\`python и т. п.
  - Исходный код и вывод консоли показывай на реальных скриншотах со ссылкой в тексте.
  - Короткие команды пиши инлайн: \`...\`; расчёты — маркированным списком.`;

    const commonRules = `ТРЕБОВАНИЯ:
${narrativeRule}
• Пиши кратко и технически точно: фиксируй действия, параметры, результаты и краткое назначение компонентов в работе. Не добавляй общеизвестную теорию и канцелярит.
• Не выдумывай факты, числа, команды, результаты, источники, изображения или имена файлов. Сохраняй реальные данные из материалов.
${mathRule}
• Таблицы используй только для числовых показателей и сопоставления данных. Не помещай в них формулы, расчёты, ход работы, команды, цели, оборудование или ПО.
  Подпись ставь над таблицей без точки: «Таблица N — Название». Перед таблицей дай ссылку «в таблице N». Используй Markdown: | Колонка 1 | Колонка 2 |.
${codeRule}
• Рисунки оформляй только так: ![Название рисунка](image.png). Название с заглавной буквы пиши внутри квадратных скобок; отдельную строку «Рисунок N — ...» не добавляй. Перед рисунком дай ссылку «на рисунке N». В заголовках, подписях и названиях таблиц точки не ставь.
• Литералы, маски, операторы * и ** и точные команды оформляй инлайн-кодом. Не заключай в обратные кавычки обычные числа и IP-адреса.
• Не добавляй поисковые маркеры [cite: 1], [citation: 1], 【1†source】 и [^1^]. Ссылки [1] допустимы только для реальных источников.
• Отделяй пустой строкой строку, заканчивающуюся двоеточием, от следующей формулы, литерала или кода.
${structureInstruction}`;

    const outputRule = `ФОРМАТ ОТВЕТА: верни весь результат внутри одного блока кода \`\`\`\`markdown ... \`\`\`\` ровно с четырьмя обратными апострофами. Не добавляй текст до или после блока.`;

    return {
      vision: {
        id: 'vision',
        title: 'По скриншотам и заданию',
        shortDesc: 'Сформировать пошаговый отчёт по скриншотам и заданию',
        icon: Layers,
        badge: 'Скриншоты',
        text: `${toneRole}
Составь лаконичный отчёт ${workFullTitle} по скриншотам и тексту задания.

Дисциплина: ${disciplineName}
Номер работы: ${numSuffix ? numSuffix.trim() : 'без номера'}
Тема работы: ${themeName}

${commonRules}
${customSection}

Оформи цель и вывод кратко, а ход работы — связным текстом или нумерованным списком. Используй только реальные имена файлов изображений из материалов.
${outputRule}

---
=== МАТЕРИАЛЫ ДЛЯ ОТЧЁТА ===
(Прикрепи скриншоты и вставь текст задания или заметок ниже этой линии)
============================`
      },

      code: {
        id: 'code',
        title: 'По исходному коду',
        shortDesc: 'Сформировать отчёт по программе и тестированию',
        icon: Code,
        badge: 'Код',
        text: `${toneRole}
Сформируй отчёт ${workFullTitle} по исходному коду программы.

Дисциплина: ${disciplineName}
Номер работы: ${numSuffix ? numSuffix.trim() : 'без номера'}
Тема работы: ${themeName}

${commonRules}
${customSection}

Описывай алгоритм, тестирование и код только по переданным материалам. Не создавай ссылки на несуществующие изображения. Объёмный код, конфигурации и логи оформляй блоками кода только если это разрешено настройкой.
${outputRule}

---
=== ИСХОДНЫЙ КОД ПРОГРАММЫ ===
(Вставь исходный код программы ниже этой линии)
==============================`
      },

      rewrite: {
        id: 'rewrite',
        title: 'Редактирование черновика по ГОСТ',
        shortDesc: 'Исправить стиль и структуру по ГОСТ',
        icon: Layers,
        badge: 'Рерайт',
        text: `${toneRole}
Отредактируй черновой отчёт ${workFullTitle} по теме «${themeName}» для дисциплины «${disciplineName}» по ГОСТ 7.32-2017 и ГОСТ 2.105-2019.

Сохрани все реальные данные, числа, вычисления, команды, логи и листинги. Не переписывай работу с нуля и ничего не выдумывай.
${commonRules}
${customSection}

В разделе «Вывод» дай 1–2 кратких предложения о достигнутой цели и решённых задачах. Не повторяй там длинные двоичные цепочки, IP-адреса и сырые логи.
${outputRule}

---
=== ИСХОДНЫЙ ЧЕРНОВИК ДЛЯ ПЕРЕРАБОТКИ ===
(Вставь свой черновой текст ниже этой линии — отредактируй именно его)
========================================`
      },

      defense: {
        id: 'defense',
        title: 'Вопросы к защите',
        shortDesc: 'Сформировать вопросы и краткие технические ответы',
        icon: Layers,
        badge: 'Защита',
        text: `${toneRole}
Сформируй 5 контрольных вопросов к защите отчёта ${workFullTitle} по теме «${themeName}» для дисциплины «${disciplineName}»${deptName ? `, кафедра «${deptName}»` : ''}${univClause}.

Дай к каждому вопросу краткий технически точный ответ на 2–3 предложения.
• Спрашивай о цели, действиях, методах и практических результатах работы.
• Не используй словарные определения и не выдумывай данные.
• Оформи нумерованным списком или подразделами; таблицы не используй.
${customSection}

${outputRule}

---
=== МАТЕРИАЛЫ ВЫПОЛНЕННОЙ РАБОТЫ ===
(Вставь сюда текст отчёта или листинг для подготовки вопросов)
====================================`
      }
    };
  }, [customInstructions, deptName, disciplineName, themeName, includeLatex, includeCodeBlocks, meta.work_type, meta.university, meta.work_number]);

  // Clean AI responses without unsafe pronoun substitution.
  const cleanAiResponse = (raw: string) => {
    let text = raw.trim();
    text = text.replace(/^(?:Конечно|Вот готовый отчет|Ниже представлен|Здравствуйте|Привет|Приветствую|Рад помочь).*?\n+/i, '');
    text = text.replace(/\n+(?:Надеюсь, этот отчет|Если нужны доработки|Удачи в сдаче|Обращайтесь|С уважением).*?$/i, '');

    // Remove verbose pseudo-academic filler.
    text = text.replace(/В рамках проведения (?:комплексного )?(?:декомпозиционного )?(?:анализа|исследования)/gi, 'В ходе анализа');
    text = text.replace(/В рамках выполнения (?:настоящей|данной)?\s*(?:лабораторной|практической|курсовой|расчетно-графической)?\s*работы/gi, 'В ходе работы');
    text = text.replace(/(?:Следует|Необходимо) (?:отметить|подчеркнуть|заметить), что\s*/gi, '');

    // Simplify verbose equipment and interface-state phrasing.
    text = text.replace(/находится в активном состоянии и обеспечивает/gi, 'активен, обеспечивает');
    text = text.replace(/находится в активном состоянии/gi, 'активен');

    // Remove AI search markers and footnotes such as [cite: 4] and [^1^].
    text = text.replace(/\[cite:\s*[^\]]+\]/gi, '');
    text = text.replace(/\[citation:\s*[^\]]+\]/gi, '');
    text = text.replace(/【\d+(?::\d+)?†source】/g, '');
    text = text.replace(/\[\^\d+\^\]/g, '');
    // Remove spaces left before punctuation after stripping footnotes.
    text = text.replace(/[ \t]+([.,;:!?])/g, '$1');

    // Extract the requested Markdown fence even when the response includes
    // introductory or closing prose.
    const fencedMatch = text.match(/(?:^|\n)(`{3,})markdown\s*\n([\s\S]*?)\n\1(?:\s*$|\n)/i);
    if (fencedMatch) {
      text = fencedMatch[2].trim();
    } else {
      const genericFence = text.match(/(?:^|\n)(`{3,})[a-z]*\s*\n([\s\S]*?)\n\1(?:\s*$|\n)/i);
      if (genericFence) {
        text = genericFence[2].trim();
      }
    }

    // Collapse single-line terminal command fences into inline code.
    text = text.replace(/(:\s*)\n+```(?:bash|sh|cmd|powershell|text)?\s*\n\s*([a-zA-Z0-9_\.\-\/\\~][^\n`]{0,80})\s*\n+```/gi, (match, colon, cmd) => {
      return ` \`${cmd.trim()}\`.`;
    });

    // Unwrap text fences containing equations, lists, or base conversions.
    text = text.replace(/```(?:text|plain)?\s*\n([\s\S]*?)\n```/gi, (match, inner) => {
      const trimmed = inner.trim();
      const hasMath = /\$[^\$\n]+\$/.test(trimmed);
      const hasRadix = /(?:\d+_{10}|[0-9a-fA-F]+_{16}|[01]+_2)\s*=/.test(trimmed);
      const hasBinaryChain = /^[01]{8}(?:-[01]{8}){2,}/m.test(trimmed);
      const hasFormulaList = /^[ \t]*[-–—]\s*(?:\$|[0-9a-fA-F]+_)/m.test(trimmed);
      if (hasMath || hasRadix || hasBinaryChain || hasFormulaList) {
        return `\n${trimmed}\n`;
      }
      return match;
    });

    text = text.replace(/^(#{1,6}\s+[^\n]+?)\.\s*$/gm, '$1');
    text = text.replace(/^===+[^=\n]+===+\s*$/gm, '');

    // Convert standalone assignment headings into aim-section prose.
    text = text.replace(/^#+\s*(?:Задание на работу|Задание|Задачи (?:лабораторной|практической|курсовой)?\s*работы|Задачи работы)\s*$/gmi, 'Для достижения цели поставлены задачи:');

    // Deduplicate a caption following its image.
    text = text.replace(/(!\[([^\]]*)\]\(([^)]+)\))\s*\n+(?:(?:\*{1,2}|_{1,2})?\s*(?:рисунок|рис\.?)\s*(?:\d+(?:\.\d+)*)?(?:\s*[:–—-]\s*([^\n*_\r]+)|)(?:\*{1,2}|_{1,2})?)(?=\n|$)/gi, (match, fullImg, alt, src, captionText) => {
      const trimmedAlt = (alt || '').trim();
      const rawCaption = (captionText || '').trim().replace(/^[*_]+|[*_]+$/g, '').trim();
      const isGenericAlt = !trimmedAlt || /^(?:image|img|рисунок|рис|иллюстрация|photo|фото|скриншот|screenshot|\d+)$/i.test(trimmedAlt) || /\.(?:png|jpe?g|svg|webp|gif)$/i.test(trimmedAlt);
      
      if ((isGenericAlt || (rawCaption && rawCaption.toLowerCase().includes(trimmedAlt.toLowerCase()))) && rawCaption) {
        return `![${rawCaption}](${src})\n\n`;
      }
      return `${fullImg}\n\n`;
    });

    // Deduplicate a caption preceding its image.
    text = text.replace(/(?:^|\n)((?:\*{1,2}|_{1,2})?\s*(?:рисунок|рис\.?)\s*(?:\d+(?:\.\d+)*)?(?:\s*[:–—-]\s*([^\n*_\r]+)|)(?:\*{1,2}|_{1,2})?)\s*\n+(!\[([^\]]*)\]\(([^)]+)\))/gi, (match, dupLine, captionText, fullImg, alt, src) => {
      const trimmedAlt = (alt || '').trim();
      const rawCaption = (captionText || '').trim().replace(/^[*_]+|[*_]+$/g, '').trim();
      const isGenericAlt = !trimmedAlt || /^(?:image|img|рисунок|рис|иллюстрация|photo|фото|скриншот|screenshot|\d+)$/i.test(trimmedAlt) || /\.(?:png|jpe?g|svg|webp|gif)$/i.test(trimmedAlt);
      
      if ((isGenericAlt || (rawCaption && rawCaption.toLowerCase().includes(trimmedAlt.toLowerCase()))) && rawCaption) {
        return `\n\n![${rawCaption}](${src})`;
      }
      return `\n\n${fullImg}`;
    });

    text = text.replace(/!\[(.*?)\.\]\((.*?)\)/g, '![$1]($2)');
    text = text.replace(/!\[(Рисунок\s+\d+(?:\.\d+)*)\s*[-–:.]\s*(.*?)\]/g, '![$1 — $2]');
    text = text.replace(/^(Таблица\s+\d+(?:\.\d+)*)\s*[-–:.]\s*(.*)$/gm, '$1 — $2');
    text = text.replace(/^(Таблица\s+\d+(?:\.\d+)*\s*—\s*.*?)\.\s*$/gm, '$1');

    // Separate colon-ended lines from code literals to prevent justification gaps.
    text = text.replace(/(:\s*)\n\s*(`[^`\n]+`|[0-9a-fA-F\-]{12,}|[01\-]{16,})/g, '$1\n\n$2');
    // Repair an isolated exponent marker by restoring the base and math delimiter.
    text = text.replace(/(?<![\$\w])\^(\d+)\s*-\s*(\d+)\s*=\s*(\d+)\$/g, (_, p1, p2, p3) => `$$2^${p1} - ${p2} = ${p3}$$`);

    let extractedTheme: string | undefined;
    const themeMatch = text.match(/(?:Тема работы|Тема):\s*([^\n]+)/i);
    if (themeMatch && themeMatch[1]) {
      extractedTheme = themeMatch[1].replace(/^[«"]|[»"]$/g, '').trim().replace(/\.$/, '');
    }

    return { cleanedText: text.trim(), extractedTheme };
  };

  const handleApply = (mode: 'replace' | 'append') => {
    if (!rawAiText.trim()) return;
    const { cleanedText, extractedTheme } = cleanAiResponse(rawAiText);
    onApplyImport(cleanedText, extractedTheme, mode);
    onClose();
  };

  const currentPromptObj = PROMPTS[selectedPromptKey];

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[92vh] flex flex-col rounded-xl bg-white shadow-xl overflow-hidden border border-slate-200">
        {/* Modal header. */}
        <div className="flex items-center justify-between border-b px-4 sm:px-5 py-3 bg-slate-50 shrink-0">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-blue-600" />
            <h3 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
              Генератор промптов для нейросети
            </h3>
          </div>
          <button 
            onClick={onClose} 
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors shrink-0"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Tab switch. */}
        <div className="flex border-b border-slate-200 bg-white px-3 sm:px-5 pt-2 gap-3 sm:gap-6 text-xs font-semibold overflow-x-auto no-scrollbar shrink-0">
          <button
            onClick={() => setActiveTab('prompts')}
            className={`pb-2 flex items-center gap-1.5 transition-all border-b-2 whitespace-nowrap ${
              activeTab === 'prompts'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <span>1. Скопировать промпт</span>
          </button>
          <button
            onClick={() => setActiveTab('import')}
            className={`pb-2 flex items-center gap-1.5 transition-all border-b-2 whitespace-nowrap ${
              activeTab === 'import'
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <ClipboardCheck className="h-3.5 w-3.5" />
            <span>2. Вставить ответ нейросети</span>
            {rawAiText.trim() && (
              <span className="ml-1 rounded-full bg-emerald-500 w-1.5 h-1.5" />
            )}
          </button>
        </div>

        {/* Modal body. */}
        <div className="flex-1 overflow-y-auto p-3 sm:p-5">
          {activeTab === 'prompts' ? (
            <div className="space-y-3.5">
              {/* Preset instructions. */}
              <div className="rounded-lg border border-slate-200 bg-slate-50/60 p-3 space-y-1 text-xs">
                <label className="text-[11px] font-semibold text-slate-700 block">
                  Кастомные требования к работе (из шаблона):
                </label>
                <textarea
                  value={customInstructions}
                  onChange={e => handleCustomInstructionsChange(e.target.value)}
                  placeholder="Дополнительные требования к работе (сохраняются в текущий шаблон)..."
                  rows={2}
                  className="w-full rounded border border-slate-300 bg-white p-2 text-xs text-slate-800 focus:border-blue-500 focus:outline-none resize-none leading-relaxed"
                />
                <div className="flex flex-wrap items-center justify-between gap-2.5 pt-1 border-t border-slate-200/70">
                  <div className="flex flex-wrap items-center gap-3">
                    <label className="flex items-center gap-1.5 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={includeLatex}
                        onChange={e => handleLatexChange(e.target.checked)}
                        className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5"
                      />
                      <span className="text-[11px] font-medium text-slate-700">Формулы в LaTeX</span>
                    </label>

                    <label className="flex items-center gap-1.5 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={includeCodeBlocks}
                        onChange={e => handleCodeBlocksChange(e.target.checked)}
                        className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-3.5 w-3.5"
                      />
                      <span className="text-[11px] font-medium text-slate-700" title="Разрешить ИИ использовать блоки текста и кода (```text, ```bash, ```python). Если выключено — работа оформляется связным текстом и скриншотами.">
                        Блоки текста / кода
                      </span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Prompt type selector. */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {(Object.keys(PROMPTS) as Array<keyof typeof PROMPTS>).map(key => {
                  const p = PROMPTS[key];
                  const IconComponent = p.icon;
                  const isSelected = selectedPromptKey === key;
                  return (
                    <button
                      key={key}
                      onClick={() => setSelectedPromptKey(key)}
                      className={`rounded-lg border p-2.5 text-left transition-all ${
                        isSelected
                          ? 'border-blue-600 bg-blue-50/50 ring-1 ring-blue-600'
                          : 'border-slate-200 bg-white hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center gap-1.5 mb-0.5">
                        <IconComponent className={`h-3.5 w-3.5 ${isSelected ? 'text-blue-600' : 'text-slate-500'}`} />
                        <span className="text-xs font-bold text-slate-800">{p.title}</span>
                      </div>
                      <p className="text-[11px] text-slate-500 leading-snug line-clamp-1">
                        {p.shortDesc}
                      </p>
                    </button>
                  );
                })}
              </div>

              {/* Generated prompt field. */}
              <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 relative space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-slate-700">
                    Готовый текст промпта:
                  </span>
                  <button
                    onClick={() => copyToClipboard(currentPromptObj.text, selectedPromptKey)}
                    className={`flex items-center gap-1 rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                      copiedKey === selectedPromptKey
                        ? 'bg-emerald-600 text-white'
                        : 'bg-blue-600 text-white hover:bg-blue-700'
                    }`}
                  >
                    {copiedKey === selectedPromptKey ? (
                      <>
                        <Check className="h-3 w-3" /> Скопировано!
                      </>
                    ) : (
                      <>
                        <Copy className="h-3 w-3" /> Скопировать
                      </>
                    )}
                  </button>
                </div>

                <pre className="max-h-56 overflow-auto rounded border border-slate-200 bg-white p-3 font-mono text-[11px] text-slate-800 whitespace-pre-wrap leading-relaxed select-all">
                  {currentPromptObj.text}
                </pre>
                {copiedKey === 'copy-error' && (
                  <p className="text-[11px] font-medium text-amber-700">
                    Не удалось скопировать автоматически — выделите текст вручную (Ctrl+A, затем Ctrl+C).
                  </p>
                )}
              </div>
            </div>
          ) : (
            /* Response import tab. */
            <div className="space-y-3 text-xs">
              <div className="flex items-center justify-between">
                <label className="font-semibold text-slate-700">
                  Вставьте ответ нейросети целиком, вместе с блоком ```markdown (Ctrl+V):
                </label>
                <div className="flex items-center gap-2">
                  {rawAiText.trim() && (
                    <button
                      onClick={() => setRawAiText('')}
                      className="text-[11px] text-slate-400 hover:text-red-600"
                    >
                      Очистить
                    </button>
                  )}
                </div>
              </div>
              <textarea
                value={rawAiText}
                onChange={e => setRawAiText(e.target.value)}
                placeholder="Вставьте ответ нейросети (включая блок ```markdown) — обрамляющие блоки кода будут удалены автоматически..."
                className="w-full h-64 rounded-lg border border-slate-300 p-3 font-mono text-xs text-slate-800 focus:border-blue-500 focus:outline-none leading-relaxed"
              />

              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-end gap-2 pt-1">
                <button
                  onClick={() => handleApply('append')}
                  disabled={!rawAiText.trim()}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                >
                  Добавить в конец
                </button>
                <button
                  onClick={() => handleApply('replace')}
                  disabled={!rawAiText.trim()}
                  className="rounded-lg bg-blue-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700 disabled:opacity-50"
                >
                  Заменить текст отчета
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Footer. */}
        <div className="border-t px-5 py-2.5 bg-slate-50 flex items-center justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-200 px-3 py-1 text-xs font-medium text-slate-700 hover:bg-slate-300"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};
