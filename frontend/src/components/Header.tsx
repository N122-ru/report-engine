import React, { useState, useRef, useEffect } from 'react';
import { 
  Download, FileText, UploadCloud, Save, FolderOpen, 
  Bot, FileCheck2, ChevronDown, Plug, BookOpen
} from 'lucide-react';
import { ReportMetadata } from '../types';

interface HeaderProps {
  meta: ReportMetadata;
  appVersion?: string;
  onDownloadDocx: () => void;
  onDownloadPdf: () => void;
  pdfExportEnabled: boolean;
  onDownloadTitleOnly: () => void;
  onOpenVerifyModal: () => void;
  onOpenAiModal: () => void;
  onOpenMcpModal: () => void;
  onOpenGuide: () => void;
  onExportJson: () => void;
  onImportJson: (e: React.ChangeEvent<HTMLInputElement>) => void;
  onExportProfile: () => void;
  onImportProfile: (e: React.ChangeEvent<HTMLInputElement>) => void;
  isGenerating: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  meta,
  appVersion,
  onDownloadDocx,
  onDownloadPdf,
  pdfExportEnabled,
  onDownloadTitleOnly,
  onOpenVerifyModal,
  onOpenAiModal,
  onOpenMcpModal,
  onOpenGuide,
  onExportJson,
  onImportJson,
  onExportProfile,
  onImportProfile,
  isGenerating
}) => {
  const [isExportMenuOpen, setIsExportMenuOpen] = useState(false);
  const [isFileMenuOpen, setIsFileMenuOpen] = useState(false);
  const exportMenuRef = useRef<HTMLDivElement | null>(null);
  const fileMenuRef = useRef<HTMLDivElement | null>(null);

  // Close dropdowns when clicking outside them.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (exportMenuRef.current && !exportMenuRef.current.contains(e.target as Node)) {
        setIsExportMenuOpen(false);
      }
      if (fileMenuRef.current && !fileMenuRef.current.contains(e.target as Node)) {
        setIsFileMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  return (
    <header className="sticky top-0 z-40 flex h-14 w-full items-center justify-between border-b border-slate-200 bg-white px-2.5 sm:px-6 shadow-sm">
      {/* Logo and title. */}
      <div className="flex items-center gap-1.5 sm:gap-3 min-w-0">
        <div className="flex h-8 w-8 sm:h-9 sm:w-9 items-center justify-center rounded-lg bg-blue-600 text-white shadow-sm shrink-0">
          <FileCheck2 className="h-4 w-4 sm:h-5 sm:w-5" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 sm:gap-2">
            <h1 className="text-xs sm:text-sm font-bold text-slate-900 tracking-tight truncate">
              Конструктор<span className="hidden min-[400px]:inline"> отчётов</span>
            </h1>
            <span className="rounded bg-slate-100 border border-slate-200 px-1 sm:px-1.5 py-0.5 text-[9px] sm:text-[10px] font-medium text-slate-600 shrink-0 hidden sm:inline-block">
              ГОСТ 7.32
            </span>
            {appVersion && (
              <span className="text-[9px] sm:text-[10px] text-slate-400 shrink-0">v{appVersion}</span>
            )}
          </div>
          <p className="text-[11px] text-slate-500 truncate max-w-xs sm:max-w-sm hidden sm:block">
            {meta.university || 'ГОСТ 7.32-2017 / ГОСТ 2.105-2019'}
          </p>
        </div>
      </div>

      {/* Action toolbar. */}
      <div className="flex items-center gap-1 sm:gap-2 shrink-0">
        {/* File menu for opening and saving projects. */}
        <div className="relative" ref={fileMenuRef}>
          <button
            type="button"
            onClick={() => setIsFileMenuOpen(!isFileMenuOpen)}
            className={`flex items-center gap-1 sm:gap-1.5 rounded-lg border px-1.5 sm:px-2.5 py-1.5 text-xs font-semibold transition-all ${
              isFileMenuOpen
                ? 'bg-slate-100 border-slate-400 text-slate-900 shadow-sm'
                : 'border-slate-300 bg-white text-slate-700 hover:bg-slate-50'
            }`}
            title="Операции с файлом проекта (.json)"
          >
            <FolderOpen className="h-3.5 w-3.5 text-slate-500" />
            <span className="hidden sm:inline">Файл</span>
            <ChevronDown className={`h-3 w-3 text-slate-400 transition-transform ${isFileMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {isFileMenuOpen && (
            <div className="absolute left-0 top-full mt-1.5 w-52 max-w-[calc(100vw-20px)] rounded-xl bg-white border border-slate-200 shadow-xl p-1.5 z-50 text-xs space-y-0.5">
              <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer font-medium">
                <FolderOpen className="h-4 w-4 text-blue-600" />
                <span>Открыть проект (.json)</span>
                <input 
                  type="file" 
                  accept=".json" 
                  onChange={e => { 
                    setIsFileMenuOpen(false); 
                    onImportJson(e); 
                  }} 
                  className="hidden" 
                />
              </label>
              <label className="flex items-center gap-2 px-2.5 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors cursor-pointer font-medium">
                <UploadCloud className="h-4 w-4 text-purple-600" />
                <span>Импортировать профиль (.json)</span>
                <input
                  type="file"
                  accept=".json,application/json"
                  onChange={e => {
                    setIsFileMenuOpen(false);
                    onImportProfile(e);
                  }}
                  className="hidden"
                />
              </label>
              <button
                type="button"
                onClick={() => {
                  setIsFileMenuOpen(false);
                  onExportJson();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors text-left font-medium"
              >
                <Save className="h-4 w-4 text-emerald-600" />
                <span>Сохранить проект (.json)</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsFileMenuOpen(false);
                  onExportProfile();
                }}
                className="w-full flex items-center gap-2 px-2.5 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors text-left font-medium"
              >
                <Save className="h-4 w-4 text-purple-600" />
                <span>Экспортировать профиль (.json)</span>
              </button>
            </div>
          )}
        </div>

        <button
          type="button"
          onClick={onOpenGuide}
          aria-label="Шпаргалка по отчёту"
          title="Как составить отчёт самостоятельно"
          className="inline-flex items-center justify-center gap-1 sm:gap-1.5 rounded-lg border border-slate-300 bg-white px-1.5 sm:px-2.5 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
        >
          <BookOpen className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="hidden min-[1280px]:inline">Шпаргалка</span>
        </button>

        <div className="h-4 w-px bg-slate-200 hidden sm:block" />

        {/* AI prompt, MCP agent, and external audit tools. */}
        <div className="flex items-center gap-1 sm:gap-1.5">
          <button
            type="button"
            onClick={onOpenMcpModal}
            className="flex items-center gap-1 sm:gap-1.5 rounded-lg border border-purple-200 bg-purple-50 px-1.5 sm:px-2.5 py-1.5 text-xs font-semibold text-purple-700 hover:bg-purple-100 active:scale-95 transition-all shadow-none"
            title="Подключить ИИ-агента (Antigravity, Cursor, Claude) прямо к этой вкладке через MCP"
          >
            <Plug className="h-3.5 w-3.5 text-purple-600" />
            <span className="hidden sm:inline">ИИ-агент (MCP)</span>
            <span className="sm:hidden">MCP</span>
          </button>

          <button
            type="button"
            onClick={onOpenAiModal}
            className="flex items-center gap-1 sm:gap-1.5 rounded-lg border border-blue-200 bg-blue-50 px-1.5 sm:px-2.5 py-1.5 text-xs font-semibold text-blue-700 hover:bg-blue-100 active:scale-95 transition-all shadow-none"
            title="Сгенерировать адаптированный промпт для нейросетей и импортировать результат"
          >
            <Bot className="h-3.5 w-3.5 text-blue-600" />
            <span className="hidden sm:inline">Промпт для ИИ</span>
            <span className="sm:hidden">ИИ</span>
          </button>

          <button
            type="button"
            onClick={onOpenVerifyModal}
            className="hidden md:flex items-center gap-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
            title="Проверить внешний файл .docx по ГОСТ 7.32"
          >
            <UploadCloud className="h-3.5 w-3.5 text-slate-500" />
            <span>Проверить .DOCX</span>
          </button>
        </div>

        <div className="h-4 w-px bg-slate-200 hidden min-[480px]:block" />

        {/* Split export button for DOCX, PDF, and title-page output. */}
        <div className="relative flex items-center shadow-sm rounded-lg" ref={exportMenuRef}>
          <button
            type="button"
            onClick={onDownloadDocx}
            disabled={isGenerating}
            className="flex items-center gap-1 sm:gap-1.5 rounded-l-lg bg-blue-600 px-2 sm:px-3.5 py-1.5 text-xs font-bold text-white hover:bg-blue-700 active:scale-95 disabled:opacity-50 transition-all border-r border-blue-500"
            title="Сгенерировать и скачать полный отчет (.docx)"
          >
            <Download className="h-3.5 w-3.5" />
            <span>{isGenerating ? 'Сборка...' : <><span className="hidden sm:inline">Скачать </span>.DOCX</>}</span>
          </button>

          <button
            type="button"
            onClick={() => setIsExportMenuOpen(!isExportMenuOpen)}
            disabled={isGenerating}
            className="rounded-r-lg bg-blue-600 px-1.5 sm:px-2 py-1.5 text-xs font-bold text-white hover:bg-blue-700 active:scale-95 disabled:opacity-50 transition-all self-stretch flex items-center justify-center"
            title="Другие форматы экспорта"
          >
            <ChevronDown className={`h-3.5 w-3.5 transition-transform ${isExportMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {isExportMenuOpen && (
            <div className="absolute right-0 top-full mt-1.5 w-56 max-w-[calc(100vw-20px)] rounded-xl bg-white border border-slate-200 shadow-xl p-1.5 z-50 text-xs space-y-0.5">
              {pdfExportEnabled ? (
                <button
                  type="button"
                  onClick={() => {
                    setIsExportMenuOpen(false);
                    onDownloadPdf();
                  }}
                  disabled={isGenerating}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors text-left font-medium"
                >
                  <FileText className="h-4 w-4 text-slate-600" />
                  <div>
                    <div className="font-semibold text-slate-800">Экспорт в PDF</div>
                    <div className="text-[10px] text-slate-400">Через локальный конвертер</div>
                  </div>
                </button>
              ) : (
                <div className="flex items-center gap-2.5 px-3 py-2 text-slate-400">
                  <FileText className="h-4 w-4" />
                  <div>
                    <div className="font-semibold">Экспорт в PDF недоступен</div>
                    <div className="text-[10px]">Откройте DOCX в Office или установите конвертер</div>
                  </div>
                </div>
              )}

              <button
                type="button"
                onClick={() => {
                  setIsExportMenuOpen(false);
                  onDownloadTitleOnly();
                }}
                disabled={isGenerating}
                className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-slate-700 hover:bg-slate-100 transition-colors text-left font-medium border-t border-slate-100"
              >
                <FileCheck2 className="h-4 w-4 text-blue-600" />
                <div>
                  <div className="font-semibold text-slate-800">Только титульный лист</div>
                  <div className="text-[10px] text-slate-400">1 страница (.docx)</div>
                </div>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
