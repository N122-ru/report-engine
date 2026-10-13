import React, { useRef, useState, useLayoutEffect, useCallback } from 'react';
import { 
  Bold, Italic, Code, Heading1, Heading2, Table, Image as ImageIcon, 
  Wand2, FileCode, Sigma, List, ListOrdered, BookOpen
} from 'lucide-react';
import { autofixMarkdown } from '../services/api';
import { MediaDrawer } from './MediaDrawer';
import { ImageLayout } from '../types';
import { mergeImageFiles } from '../services/media';
import { EditorSelection, insertEditorText } from '../services/editorInsertion';

interface MarkdownEditorProps {
  content: string;
  onChange: (newContent: string) => void;
  images: File[];
  onImagesChange: (imgs: File[]) => void;
  imageLayouts?: Record<string, ImageLayout>;
  onImageLayoutChange: (name: string, layout: ImageLayout) => void;
  onOpenTableModal: () => void;
  onRegisterInsert?: (insertFn: ((text: string) => void) | null) => void;
  selectionRef?: React.RefObject<EditorSelection>;
}

export const MarkdownEditor: React.FC<MarkdownEditorProps> = ({
  content,
  onChange,
  images,
  onImagesChange,
  imageLayouts,
  onImageLayoutChange,
  onOpenTableModal,
  onRegisterInsert,
  selectionRef
}) => {
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const localSelectionRef = useRef<EditorSelection>({ start: 0, end: 0 });
  const storedSelectionRef = selectionRef || localSelectionRef;
  const [isFixing, setIsFixing] = useState(false);
  const [fixMessage, setFixMessage] = useState<string | null>(null);
  const [isT9Enabled, setIsT9Enabled] = useState(true);
  const [isMediaDrawerOpen, setIsMediaDrawerOpen] = useState(false);

  const rememberSelection = (ta: HTMLTextAreaElement) => {
    storedSelectionRef.current = { start: ta.selectionStart, end: ta.selectionEnd };
  };

  useLayoutEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.setSelectionRange(storedSelectionRef.current.start, storedSelectionRef.current.end);
    rememberSelection(ta);
    return () => rememberSelection(ta);
  }, [storedSelectionRef]);

  // Insert text at the current selection.
  const insertText = useCallback((before: string, after: string = '', defaultText: string = '', replaceSelection = false) => {
    const ta = textareaRef.current;
    if (!ta) return;
    const insertion = insertEditorText(ta.value, { start: ta.selectionStart, end: ta.selectionEnd }, {
      before, after, defaultText, replaceSelection,
    });
    storedSelectionRef.current = insertion.selection;
    onChange(insertion.content);

    setTimeout(() => {
      if (textareaRef.current !== ta || !ta.isConnected || ta.value !== insertion.content) return;
      ta.focus();
      ta.setSelectionRange(insertion.selection.start, insertion.selection.end);
      storedSelectionRef.current = insertion.selection;
    }, 0);
  }, [onChange, storedSelectionRef]);

  useLayoutEffect(() => {
    if (onRegisterInsert) {
      onRegisterInsert((text: string) => {
        insertText(text, '', '', true);
      });
      return () => onRegisterInsert(null);
    }
  }, [onRegisterInsert, insertText]);

  // Accept screenshot paste events.
  const handlePaste = (e: React.ClipboardEvent) => {
    const items = e.clipboardData?.items;
    if (!items) return;

    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        const file = items[i].getAsFile();
        if (file) {
          const timestamp = Date.now();
          const imgName = `screenshot_${timestamp}.png`;
          const renamedFile = new File([file], imgName, { type: file.type });

          onImagesChange([...images, renamedFile]);
          insertText(`\n![Результат выполнения](${imgName})\n`);
        }
        return;
      }
    }
  };

  // File-picker upload handler.
  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addDroppedImages(e.target.files);
    }
    e.target.value = '';
  };

  const addDroppedImages = (files: FileList) => {
    const result = mergeImageFiles(images, files);
    setFixMessage(result.rejected.length ? `Не являются изображениями: ${result.rejected.join(', ')}`
      : result.duplicates.length ? `Уже прикреплены: ${result.duplicates.join(', ')}` : null);
    if (!result.added.length) return;
    onImagesChange(result.images);
    insertText(`\n\n${result.added.map(file => `![Иллюстрация к разделу](<${file.name}>)`).join('\n\n')}\n\n`);
  };

  // Request backend typography fixes.
  const handleAutofix = async () => {
    setIsFixing(true);
    setFixMessage(null);
    try {
      const res = await autofixMarkdown(content);
      onChange(res.fixed_content);
      if (res.fixes_applied.length > 0) {
        setFixMessage(`Применено исправлений: ${res.fixes_applied.length}`);
      } else {
        setFixMessage("Ошибок оформления нет");
      }
      setTimeout(() => setFixMessage(null), 4000);
    } catch {
      setFixMessage("Ошибка при обращении к линтеру");
    } finally {
      setIsFixing(false);
    }
  };

  return (
    <div className="flex flex-col rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden h-full flex-1 min-h-0">
      {/* Toolbar. */}
      <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/90 px-2 sm:px-3 py-1.5 text-xs gap-1 sm:gap-1.5 overflow-x-auto no-scrollbar shrink-0">
        <div className="flex items-center gap-1 shrink-0">
          {/* Text formatting. */}
          <button
            type="button"
            onClick={() => insertText('**', '**', 'жирный текст')}
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200"
            title="Жирный (Ctrl+B)"
          >
            <Bold className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => insertText('*', '*', 'курсив')}
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200"
            title="Курсив (Ctrl+I)"
          >
            <Italic className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => insertText('`', '`', 'код')}
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200"
            title="Инлайн код"
          >
            <Code className="h-4 w-4" />
          </button>

          <div className="h-4 w-px bg-slate-300 mx-1 hidden sm:block" />

          {/* Headings. */}
          <button
            type="button"
            onClick={() => insertText('\n# ', '\n', 'Заголовок раздела')}
            className="rounded p-1.5 font-bold text-slate-700 hover:bg-slate-200"
            title="Заголовок 1 уровня (# Цель работы)"
          >
            <Heading1 className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={() => insertText('\n## ', '\n', 'Подраздел')}
            className="rounded p-1.5 font-bold text-slate-700 hover:bg-slate-200"
            title="Заголовок 2 уровня (## 1. Ход работы)"
          >
            <Heading2 className="h-4 w-4" />
          </button>

          <div className="h-4 w-px bg-slate-300 mx-1 hidden sm:block" />

          {/* GOST 7.32 lists. */}
          <button
            type="button"
            onClick={() => insertText('\n1. ', '\n', 'Пункт')}
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200"
            title="Нумерованный список хода работы (1. Пункт)"
          >
            <ListOrdered className="h-4 w-4 text-slate-700" />
          </button>
          <button
            type="button"
            onClick={() => insertText('\n- ', '\n', 'Элемент')}
            className="rounded p-1.5 text-slate-600 hover:bg-slate-200"
            title="Маркированный перечень (– Элемент)"
          >
            <List className="h-4 w-4 text-slate-700" />
          </button>

          <div className="h-4 w-px bg-slate-300 mx-1 hidden sm:block" />

          {/* Structural block shortcuts. */}
          <button
            type="button"
            onClick={() => insertText('$', '$', 'n = 8')}
            className="flex items-center gap-1 rounded bg-slate-200/80 px-2 py-1 font-semibold text-slate-700 hover:bg-slate-300 transition-colors"
            title="Вставить формулу LaTeX ($n = 8$, $2^8 - 2 = 254$)"
          >
            <Sigma className="h-3.5 w-3.5 text-amber-600" />
            <span className="hidden sm:inline">Формула</span>
          </button>

          <button
            type="button"
            onClick={() => insertText('\n```bash\n', '\n```\n', '# Вставьте команды')}
            className="flex items-center gap-1 rounded bg-slate-200/80 px-2 py-1 font-semibold text-slate-700 hover:bg-slate-300 transition-colors"
            title="Вставить листинг программного кода"
          >
            <FileCode className="h-3.5 w-3.5 text-blue-600" />
            <span className="hidden sm:inline">Листинг</span>
          </button>

          <button
            type="button"
            onClick={onOpenTableModal}
            className="flex items-center gap-1 rounded bg-slate-200/80 px-2 py-1 font-semibold text-slate-700 hover:bg-slate-300 transition-colors"
            title="Конструктор таблицы по ГОСТ"
          >
            <Table className="h-3.5 w-3.5 text-emerald-600" />
            <span className="hidden sm:inline">Таблица</span>
          </button>

          <button
            type="button"
            onClick={() => setIsMediaDrawerOpen(prev => !prev)}
            className={`flex items-center gap-1.5 rounded px-2.5 py-1 font-semibold text-xs transition-all ${
              isMediaDrawerOpen
                ? 'bg-purple-600 text-white shadow-sm'
                : 'bg-purple-50 text-purple-700 hover:bg-purple-100 border border-purple-200'
            }`}
            title="Открыть шторку скриншотов и иллюстраций"
          >
            <ImageIcon className="h-3.5 w-3.5" />
            <span>Медиа</span>
            <span className={`px-1.5 py-0.2 rounded-full text-[10px] font-extrabold ${
              isMediaDrawerOpen ? 'bg-white/25 text-white' : 'bg-purple-200/80 text-purple-900'
            }`}>
              {images.length}
            </span>
          </button>

          <button
            type="button"
            onClick={() => insertText('\n\n# Список использованных источников\n1. \n2. \n', '', '')}
            className="flex items-center gap-1 rounded bg-slate-200/80 px-2 py-1 font-semibold text-slate-700 hover:bg-slate-300 transition-colors"
            title="Вставить раздел 'Список использованных источников' по ГОСТ"
          >
            <BookOpen className="h-3.5 w-3.5 text-indigo-600" />
            <span className="hidden sm:inline">Источники</span>
          </button>

          <div className="h-4 w-px bg-slate-300 mx-1 hidden sm:block" />

          {/* Browser spellcheck toggle; highlighting only. */}
          <button
            type="button"
            onClick={() => setIsT9Enabled(!isT9Enabled)}
            className={`flex items-center gap-1 rounded border px-2 py-1 font-semibold text-xs transition-all ${
              isT9Enabled
                ? 'bg-blue-50 border-blue-300 text-blue-800'
                : 'bg-slate-100 border-slate-300 text-slate-500 hover:bg-slate-200'
            }`}
            title="Т9: подсветка возможных ошибок в браузере без автоисправления текста"
          >
            <span>Т9: {isT9Enabled ? 'вкл' : 'выкл'}</span>
          </button>

          {/* Fixed-position autofix button. */}
          <button
            type="button"
            onClick={handleAutofix}
            disabled={isFixing}
            className="flex items-center gap-1 rounded bg-emerald-50 border border-emerald-300 px-2.5 py-1 font-bold text-emerald-800 hover:bg-emerald-100 active:scale-95 transition-all disabled:opacity-50"
            title="Автоматически убрать точки в заголовках, исправить тире в подписях и неразрывные пробелы по ГОСТ"
          >
            <Wand2 className="h-3.5 w-3.5 text-emerald-600" />
            <span className="hidden sm:inline">Автоисправление</span>
            <span className="sm:hidden">Авто</span>
          </button>
        </div>
      </div>

      {/* Markdown editor and media drawer. */}
      <div className="flex-1 relative flex min-h-0 overflow-hidden">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={e => {
            rememberSelection(e.currentTarget);
            onChange(e.target.value);
          }}
          onSelect={e => rememberSelection(e.currentTarget)}
          onBlur={e => rememberSelection(e.currentTarget)}
          onPaste={handlePaste}
          onDragOver={event => {
            if (!Array.from(event.dataTransfer.types).includes('Files')) return;
            event.preventDefault();
            event.dataTransfer.dropEffect = 'copy';
          }}
          onDrop={event => {
            if (!event.dataTransfer.files.length) return;
            event.preventDefault();
            addDroppedImages(event.dataTransfer.files);
          }}
          aria-label="Текст отчёта в Markdown"
          placeholder="Пишите отчет в Markdown. Нажмите Ctrl+V для быстрой вставки скриншота прямо в текст..."
          className="w-full h-full min-h-[160px] sm:min-h-[220px] lg:min-h-0 p-3 sm:p-4 font-mono text-sm leading-relaxed text-slate-800 resize-none overflow-y-auto focus:outline-none focus:ring-0 selection:bg-blue-100"
          spellCheck={isT9Enabled}
        />

        <MediaDrawer
          isOpen={isMediaDrawerOpen}
          onClose={() => setIsMediaDrawerOpen(false)}
          images={images}
          onImagesChange={onImagesChange}
          imageLayouts={imageLayouts}
          onImageLayoutChange={onImageLayoutChange}
          onInsertImage={(fileName, alt) => {
            insertText(`\n\n![${alt || 'Иллюстрация'}](${fileName})\n\n`);
          }}
          markdownContent={content}
        />
      </div>

      {/* Status bar with counters and autofix results. */}
      <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50/60 px-3 py-1 text-[11px]">
        <span className="text-slate-400">Символов: {content.length}</span>
        {fixMessage && (
          <span role="status" className="min-w-0 break-words text-right font-semibold text-slate-700">{fixMessage}</span>
        )}
      </div>
    </div>
  );
};
