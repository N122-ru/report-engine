import React, { useState } from 'react';
import { UploadCloud, X } from 'lucide-react';

interface ImportDocxModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportDocx: (file: File, mode: 'replace' | 'append', applyMeta: boolean) => Promise<void>;
}

export const ImportDocxModal: React.FC<ImportDocxModalProps> = ({
  isOpen,
  onClose,
  onImportDocx
}) => {
  const [docxMode, setDocxMode] = useState<'replace' | 'append'>('replace');
  const [applyDocxMeta, setApplyDocxMeta] = useState(true);
  const [docxImporting, setDocxImporting] = useState(false);
  const [docxError, setDocxError] = useState<string | null>(null);

  const handleDocxChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setDocxError(null);
    setDocxImporting(true);
    try {
      await onImportDocx(file, docxMode, applyDocxMeta);
      onClose();
    } catch (error) {
      setDocxError(error instanceof Error ? error.message : 'Не удалось импортировать DOCX');
    } finally {
      setDocxImporting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-xl bg-white shadow-xl overflow-hidden border border-slate-200">
        <div className="flex items-center justify-between border-b px-4 sm:px-5 py-3 bg-slate-50">
          <div className="flex items-center gap-2">
            <UploadCloud className="h-4 w-4 text-blue-600" />
            <h3 className="text-xs sm:text-sm font-bold text-slate-900 truncate">
              Импорт существующего отчёта DOCX
            </h3>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors shrink-0"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-3 sm:p-5 space-y-3 text-xs">
          <p className="text-[11px] leading-relaxed text-slate-600">
            Текст и встроенные изображения будут преобразованы в редактируемый Markdown. Исходная вёрстка Word не сохраняется.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <label className="inline-flex cursor-pointer items-center justify-center rounded-md bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-blue-700 has-[:disabled]:cursor-wait has-[:disabled]:opacity-60">
              {docxImporting ? 'Импортирование…' : 'Выбрать DOCX'}
              <input
                type="file"
                accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                onChange={handleDocxChange}
                disabled={docxImporting}
                className="sr-only"
              />
            </label>
            <select
              value={docxMode}
              onChange={event => setDocxMode(event.target.value as 'replace' | 'append')}
              disabled={docxImporting}
              aria-label="Режим импорта DOCX"
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-700"
            >
              <option value="replace">Заменить текущий текст</option>
              <option value="append">Добавить в конец</option>
            </select>
            <label className="inline-flex items-center gap-1.5 text-[11px] text-slate-700">
              <input
                type="checkbox"
                checked={applyDocxMeta}
                onChange={event => setApplyDocxMeta(event.target.checked)}
                disabled={docxImporting}
                className="h-3.5 w-3.5 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
              />
              Применить подсказки титульного листа
            </label>
          </div>
          {docxError && (
            <p role="alert" className="text-[11px] leading-relaxed text-red-700">{docxError}</p>
          )}
        </div>

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
