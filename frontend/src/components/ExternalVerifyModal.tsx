import React, { useState } from 'react';
import { X, UploadCloud, CheckCircle, AlertTriangle, XCircle, FileText, Loader2 } from 'lucide-react';
import { verifyExternalFile } from '../services/api';
import { LinterResult } from '../types';

interface ExternalVerifyModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ExternalVerifyModal: React.FC<ExternalVerifyModalProps> = ({ isOpen, onClose }) => {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LinterResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const f = e.dataTransfer.files[0];
      if (f.name.endsWith('.docx')) {
        setFile(f);
        runAudit(f);
      } else {
        setError('Пожалуйста, загрузите файл формата .docx');
      }
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const f = e.target.files[0];
      setFile(f);
      runAudit(f);
    }
    e.target.value = '';
  };

  const runAudit = async (f: File) => {
    setLoading(true);
    setError(null);
    try {
      const data = await verifyExternalFile(f);
      setResult(data);
    } catch (err: any) {
      setError(err.message || 'Ошибка при аудите файла');
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-2 sm:p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl bg-white shadow-2xl overflow-hidden">
        {/* Header. */}
        <div className="flex items-center justify-between border-b px-4 sm:px-6 py-3 sm:py-4 bg-slate-50">
          <div className="flex items-center gap-2">
            <UploadCloud className="h-5 w-5 text-indigo-600" />
            <h3 className="text-base sm:text-lg font-bold text-slate-800">Нормоконтроль стороннего .DOCX</h3>
          </div>
          <button type="button" autoFocus onClick={onClose} aria-label="Закрыть проверку .DOCX" className="rounded-lg p-1 text-slate-600 hover:bg-slate-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body. */}
        <div className="p-4 sm:p-6 overflow-y-auto space-y-4 sm:space-y-6">
          {/* Upload area. */}
          <div
            onDragOver={e => e.preventDefault()}
            onDrop={handleDrop}
            className="flex flex-col items-center justify-center border-2 border-dashed border-slate-300 rounded-xl p-6 text-center hover:border-indigo-500 bg-slate-50/50 cursor-pointer transition-colors"
            onClick={() => document.getElementById('external-file-input')?.click()}
          >
            <input
              id="external-file-input"
              type="file"
              accept=".docx"
              onChange={handleFileChange}
              className="hidden"
            />
            <FileText className="h-10 w-10 text-indigo-500 mb-2" />
            <p className="text-sm font-semibold text-slate-700">
              {file ? file.name : 'Перетащите сюда готовый отчет (.docx) или выберите файл'}
            </p>
            <p className="text-xs text-slate-500 mt-1">Проверка по ГОСТ 7.32-2017 и ГОСТ 2.105-2019</p>
          </div>

          {loading && (
            <div className="flex items-center justify-center gap-2 py-8 text-indigo-600">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span className="text-sm font-medium">Анализируем OpenXML структуру документа...</span>
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-red-50 p-4 border border-red-200 text-sm text-red-700">
              {error}
            </div>
          )}

          {result && !loading && (
            <div className="space-y-4">
              {/* Score and status. */}
              <div className="flex items-center justify-between p-4 rounded-xl bg-slate-100 border border-slate-200">
                <div>
                  <div className="text-xs font-semibold uppercase text-slate-500">Оценка соответствия</div>
                  <div className={`text-2xl font-black ${result.score >= 90 ? 'text-emerald-600' : result.score >= 70 ? 'text-amber-600' : 'text-red-600'}`}>
                    {result.score} / 100 баллов
                  </div>
                </div>
                <div>
                  {result.is_valid ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">
                      <CheckCircle className="h-4 w-4" /> Пройдено
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-red-100 text-red-800">
                      <XCircle className="h-4 w-4" /> Нарушения ГОСТ
                    </span>
                  )}
                </div>
              </div>

              {/* Metrics. */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-center text-xs">
                <div className="p-2 bg-slate-50 rounded-lg border">
                  <span className="text-slate-500">Поля (Л/П/В/Н):</span>
                  <div className="font-semibold text-slate-800">
                    {result.metrics.margins_mm.left}/{result.metrics.margins_mm.right}/{result.metrics.margins_mm.top}/{result.metrics.margins_mm.bottom} мм
                  </div>
                </div>
                <div className="p-2 bg-slate-50 rounded-lg border">
                  <span className="text-slate-500">Пустые строки ¶:</span>
                  <div className={`font-semibold ${result.metrics.empty_paragraphs_count > 5 ? 'text-red-600' : 'text-slate-800'}`}>
                    {result.metrics.empty_paragraphs_count} шт.
                  </div>
                </div>
                <div className="p-2 bg-slate-50 rounded-lg border">
                  <span className="text-slate-500">Иллюстраций / Таблиц:</span>
                  <div className="font-semibold text-slate-800">
                    {result.metrics.figures_count} / {result.metrics.tables_count}
                  </div>
                </div>
              </div>

              {/* Errors. */}
              {result.errors.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-red-700 mb-2">
                    Ошибки ({result.errors.length}):
                  </h4>
                  <div className="space-y-2">
                    {result.errors.map((err, i) => (
                      <div key={i} className="rounded-lg bg-red-50 border border-red-200 p-3 text-xs text-red-800 flex items-start gap-2">
                        <XCircle className="h-4 w-4 text-red-600 shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold">{err.message}</p>
                          <p className="text-red-600/80 mt-0.5">Место: {err.location}</p>
                          {err.fix_suggestion && (
                            <p className="text-red-700 font-medium mt-1">{err.fix_suggestion}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Warnings. */}
              {result.warnings.length > 0 && (
                <div>
                  <h4 className="text-xs font-bold uppercase tracking-wider text-amber-700 mb-2">
                    Предупреждения ({result.warnings.length}):
                  </h4>
                  <div className="space-y-2">
                    {result.warnings.map((warn, i) => (
                      <div key={i} className="rounded-lg bg-amber-50 border border-amber-200 p-3 text-xs text-amber-800 flex items-start gap-2">
                        <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0 mt-0.5" />
                        <div>
                          <p className="font-semibold">{warn.message}</p>
                          <p className="text-amber-700/80 mt-0.5">Место: {warn.location}</p>
                          {warn.fix_suggestion && (
                            <p className="text-amber-800 font-medium mt-1">{warn.fix_suggestion}</p>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer. */}
        <div className="border-t px-4 sm:px-6 py-2.5 sm:py-3 bg-slate-50 flex justify-end">
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 px-4 py-2 text-sm font-semibold text-white hover:bg-slate-900"
          >
            Закрыть
          </button>
        </div>
      </div>
    </div>
  );
};
