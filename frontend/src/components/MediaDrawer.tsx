import React, { useRef, useState, useEffect, useMemo } from 'react';
import { ImageLayout } from '../types';
import { mergeImageFiles, sortMediaFiles, MediaSort } from '../services/media';
import { 
  X, UploadCloud, Trash2, Plus, Image as ImageIcon, 
  CheckCircle2, AlertCircle
} from 'lucide-react';

interface MediaDrawerProps {
  isOpen: boolean;
  onClose: () => void;
  images: File[];
  onImagesChange: (files: File[]) => void;
  imageLayouts?: Record<string, ImageLayout>;
  onImageLayoutChange: (name: string, layout: ImageLayout) => void;
  onInsertImage: (fileName: string, altText?: string) => void;
  markdownContent: string;
}

type PendingDeletion = { kind: 'single'; name: string } | { kind: 'all' };

export const MediaDrawer: React.FC<MediaDrawerProps> = ({
  isOpen,
  onClose,
  images,
  onImagesChange,
  imageLayouts = {},
  onImageLayoutChange,
  onInsertImage,
  markdownContent
}) => {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const deleteDialogRef = useRef<HTMLDialogElement>(null);
  const cancelDeleteRef = useRef<HTMLButtonElement>(null);
  const closeDrawerRef = useRef<HTMLButtonElement>(null);
  const deleteTriggerRef = useRef<HTMLElement | null>(null);
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [altInputs, setAltInputs] = useState<Record<string, string>>({});
  const [pendingDeletion, setPendingDeletion] = useState<PendingDeletion | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const dragDepthRef = useRef(0);
  const [fileMessage, setFileMessage] = useState<string | null>(null);
  const [sort, setSort] = useState<MediaSort>(() => {
    try {
      const stored = localStorage.getItem('report_media_sort');
      if (stored === 'name-desc' || stored === 'size-desc') return stored;
    } catch {}
    return 'name-asc';
  });
  const sortedImages = useMemo(() => sortMediaFiles(images, sort), [images, sort]);

  useEffect(() => {
    try { localStorage.setItem('report_media_sort', sort); } catch {}
  }, [sort]);

  // Manage object URLs for image previews.
  useEffect(() => {
    const urls: Record<string, string> = {};
    images.forEach(img => {
      urls[img.name] = URL.createObjectURL(img);
    });
    setPreviews(urls);

    return () => {
      Object.values(urls).forEach(u => URL.revokeObjectURL(u));
    };
  }, [images]);

  useEffect(() => {
    const dialog = deleteDialogRef.current;
    if (!dialog) return;
    if (pendingDeletion && !dialog.open) {
      dialog.showModal();
      cancelDeleteRef.current?.focus();
    } else if (!pendingDeletion && dialog.open) {
      dialog.close();
      if (deleteTriggerRef.current?.isConnected) deleteTriggerRef.current.focus();
      else closeDrawerRef.current?.focus();
    }
  }, [pendingDeletion]);

  if (!isOpen) return null;

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const result = mergeImageFiles(images, files);
    const messages = [];
    if (result.rejected.length) messages.push(`Не являются изображениями: ${result.rejected.join(', ')}`);
    if (result.duplicates.length) messages.push(`Уже прикреплены: ${result.duplicates.join(', ')}`);
    setFileMessage(messages.join('. ') || null);
    if (result.added.length) onImagesChange(result.images);
  };

  const requestDeletion = (deletion: PendingDeletion) => {
    deleteTriggerRef.current = document.activeElement as HTMLElement;
    setAcknowledged(false);
    setPendingDeletion(deletion);
  };

  const confirmDeletion = () => {
    if (!pendingDeletion || (pendingDeletion.kind === 'all' && !acknowledged)) return;
    onImagesChange(pendingDeletion.kind === 'all' ? [] : images.filter(img => img.name !== pendingDeletion.name));
    setAltInputs(prev => pendingDeletion.kind === 'all'
      ? {}
      : Object.fromEntries(Object.entries(prev).filter(([name]) => name !== pendingDeletion.name)));
    setPendingDeletion(null);
  };

  const isImageInserted = (name: string) => {
    const outsideCode = markdownContent.split(/(```[\s\S]*?```)/g).filter((_, i) => i % 2 === 0).join('\n');
    const canonical = (value: string) => value.toLowerCase().replace(/[\s_()-]+/g, '');
    return [...outsideCode.matchAll(/!\[[^\]]*\]\((?:<([^>]+)>|([^\)]+))\)/g)].some(match => {
      let src = match[1] || match[2];
      try { src = decodeURIComponent(src); } catch {}
      return canonical(src.split(/[/\\]/).pop() || src) === canonical(name);
    });
  };

  return (
    <div
      className="absolute inset-y-0 right-0 z-30 w-full sm:w-96 max-w-full bg-white border-l border-slate-200 shadow-2xl flex flex-col"
      onDragEnter={event => {
        if (!Array.from(event.dataTransfer.types).includes('Files')) return;
        event.preventDefault();
        event.stopPropagation();
        dragDepthRef.current++;
        setIsDragging(true);
      }}
      onDragOver={event => {
        if (!Array.from(event.dataTransfer.types).includes('Files')) return;
        event.preventDefault();
        event.stopPropagation();
        event.dataTransfer.dropEffect = 'copy';
      }}
      onDragLeave={event => {
        event.stopPropagation();
        dragDepthRef.current = Math.max(0, dragDepthRef.current - 1);
        if (dragDepthRef.current === 0) setIsDragging(false);
      }}
      onDrop={event => {
        if (event.dataTransfer.files.length === 0) return;
        event.preventDefault();
        event.stopPropagation();
        dragDepthRef.current = 0;
        setIsDragging(false);
        handleFiles(event.dataTransfer.files);
      }}
    >
      {/* Drawer header. */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-slate-50/80 shrink-0">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-600 text-white shadow-sm">
            <ImageIcon className="h-4 w-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold text-slate-900">Иллюстрации и схемы</h3>
            <p className="text-[10px] text-slate-500">Прикреплено: {images.length}</p>
          </div>
        </div>
        <button
          ref={closeDrawerRef}
          type="button"
          onClick={() => {
            dragDepthRef.current = 0;
            setIsDragging(false);
            onClose();
          }}
          className="rounded-md p-1 text-slate-400 hover:bg-slate-200 hover:text-slate-700 transition-colors"
          aria-label="Закрыть медиа"
          title="Закрыть шторку"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      {/* Upload drop zone. */}
      <div className="p-3 border-b border-slate-100 shrink-0 bg-slate-50/50">
        <input
          type="file"
          ref={fileInputRef}
          onChange={e => {
            handleFiles(e.target.files);
            e.target.value = '';
          }}
          multiple
          accept="image/*,.png,.jpg,.jpeg,.gif,.webp,.bmp,.svg,.tif,.tiff,.avif,.ico"
          aria-label="Файлы изображений"
          className="hidden"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          className={`w-full min-h-20 border-2 border-dashed rounded-lg p-3 flex flex-col items-center justify-center text-center transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-600 ${isDragging ? 'border-purple-600 bg-purple-50' : 'border-purple-200 bg-white hover:border-purple-400 hover:bg-purple-50/30'}`}
        >
          <UploadCloud className="h-6 w-6 text-purple-600 mb-1" aria-hidden="true" />
          <span className="text-xs font-semibold text-slate-700">Добавить изображения</span>
        </button>
        {fileMessage && <p role="status" className="mt-2 break-words text-xs text-amber-800">{fileMessage}</p>}
        <label className="mt-3 flex items-center justify-between gap-2 text-xs text-slate-600">
          Сортировка
          <select value={sort} onChange={event => setSort(event.target.value as MediaSort)} className="min-w-0 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-slate-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-600">
            <option value="name-asc">По имени: А-Я</option>
            <option value="name-desc">По имени: Я-А</option>
            <option value="size-desc">Сначала большие</option>
          </select>
        </label>
      </div>

      {/* Image list. */}
      <div className="flex-1 overflow-y-auto p-3 space-y-3 min-h-0">
        {images.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-4 text-slate-400">
            <ImageIcon className="h-10 w-10 text-slate-300 stroke-[1.5] mb-2" />
            <span className="text-xs font-semibold text-slate-600">Нет прикрепленных файлов</span>
          </div>
        ) : (
          sortedImages.map(img => {
            const inserted = isImageInserted(img.name);
            const currentAlt = altInputs[img.name] ?? '';
            const canonical = (name: string) => name.toLowerCase().replace(/[\s_()-]+/g, '');
            const matching = Object.keys(imageLayouts).filter(name => canonical(name) === canonical(img.name));
            const layoutKey = img.name in imageLayouts ? img.name : (matching.length === 1 ? matching[0] : img.name);
            const layout = imageLayouts[layoutKey] || {};
            const updateLayout = (patch: ImageLayout) => onImageLayoutChange(layoutKey, { ...layout, ...patch });

            return (
              <div
                key={img.name}
                className={`rounded-lg border p-2.5 transition-colors ${
                  inserted 
                    ? 'border-slate-200 bg-white' 
                    : 'border-amber-200 bg-amber-50/30 shadow-sm'
                }`}
              >
                {/* Preview and image details. */}
                <div className="flex gap-2.5 items-start">
                  <div className="h-14 w-14 shrink-0 rounded-lg overflow-hidden bg-slate-100 border border-slate-200 relative group">
                    {previews[img.name] ? (
                      <img
                        src={previews[img.name]}
                        alt={img.name}
                        draggable={false}
                        className="h-full w-full object-cover"
                      />
                    ) : (
                      <div className="h-full w-full flex items-center justify-center text-slate-400">
                        <ImageIcon className="h-5 w-5" />
                      </div>
                    )}
                  </div>

                  <div className="flex-1 min-w-0">
                    <span 
                      className="block text-[11px] font-bold text-slate-800 truncate" 
                      title={img.name}
                    >
                      {img.name}
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {(img.size / 1024).toFixed(1)} КБ
                    </span>

                    <div className="mt-1 flex items-center gap-1">
                      {inserted ? (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-1.5 py-0.5 rounded">
                          <CheckCircle2 className="h-3 w-3" />
                          В отчете
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] font-bold text-amber-700 bg-amber-100/60 px-1.5 py-0.5 rounded">
                          <AlertCircle className="h-3 w-3" />
                          Не вставлен
                        </span>
                      )}
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => requestDeletion({ kind: 'single', name: img.name })}
                    className="p-1 rounded-md text-slate-400 hover:text-red-600 hover:bg-red-50 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
                    aria-label={`Удалить файл ${img.name}`}
                    title="Удалить файл"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>

                {/* Caption field and insertion button. */}
                <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center gap-1.5">
                  <input
                    type="text"
                    placeholder="Подпись (например: Схема стенда)"
                    aria-label={`Подпись рисунка ${img.name}`}
                    value={currentAlt}
                    onChange={e => setAltInputs({ ...altInputs, [img.name]: e.target.value })}
                    className="flex-1 min-w-0 rounded-md border border-slate-200 px-2 py-1 text-[11px] text-slate-800 placeholder-slate-400 focus:border-purple-500 focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-600"
                  />
                  <button
                    onClick={() => onInsertImage(img.name, currentAlt || 'Иллюстрация')}
                    className="shrink-0 flex items-center gap-1 rounded-md bg-purple-600 hover:bg-purple-700 text-white px-2.5 py-1 text-[11px] font-bold transition-colors shadow-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-600"
                    title="Вставить в текст по ГОСТ"
                  >
                    <Plus className="h-3 w-3" />
                    <span>Вставить</span>
                  </button>
                </div>
                <details className="mt-2 border-t border-slate-100 pt-2 text-[11px] text-slate-700">
                  <summary className="cursor-pointer font-semibold focus-visible:outline focus-visible:outline-2 focus-visible:outline-purple-600">Размещение в документе</summary>
                  <div className="mt-2 grid grid-cols-2 gap-2">
                    <label className="flex flex-col gap-1">Ширина: {layout.width_percent ?? 94}%
                      <input type="range" min="10" max="100" value={layout.width_percent ?? 94} onChange={e => updateLayout({ width_percent: Number(e.target.value) })} aria-label={`Ширина рисунка ${img.name}, процентов`} />
                    </label>
                    <label className="flex flex-col gap-1">Высота до {layout.max_height_mm ?? 200} мм
                      <input type="range" min="30" max="220" step="10" value={layout.max_height_mm ?? 200} onChange={e => updateLayout({ max_height_mm: Number(e.target.value) })} aria-label={`Максимальная высота рисунка ${img.name}, мм`} />
                    </label>
                    <label className="flex flex-col gap-1">Выравнивание
                      <select value={layout.align ?? 'center'} onChange={e => updateLayout({ align: e.target.value as ImageLayout['align'] })} className="rounded-md border border-slate-300 bg-white px-1.5 py-1">
                        <option value="center">По центру</option>
                        <option value="left">Слева</option>
                        <option value="right">Справа</option>
                      </select>
                    </label>
                    <label className="flex items-center gap-1.5">
                      <input type="checkbox" checked={layout.page_break_before ?? false} onChange={e => updateLayout({ page_break_before: e.target.checked })} />
                      С новой страницы
                    </label>
                    <label className="col-span-2 flex items-center gap-1.5">
                      <input type="checkbox" checked={layout.keep_caption_with_image ?? true} onChange={e => updateLayout({ keep_caption_with_image: e.target.checked })} />
                      Сохранять подпись рядом с рисунком
                    </label>
                  </div>
                </details>
              </div>
            );
          })
        )}
      </div>

      {/* Drawer footer. */}
      <div className="flex flex-wrap items-center justify-between gap-2 p-3 border-t border-slate-200 bg-slate-50 text-[10px] text-slate-500 shrink-0">
        <span>Размещение рисунков учитывается при скачивании DOCX и PDF</span>
        {images.length > 0 && (
          <button
            type="button"
            onClick={() => requestDeletion({ kind: 'all' })}
            className="inline-flex items-center gap-1 rounded-md px-2 py-1 font-semibold text-slate-600 hover:bg-red-50 hover:text-red-700 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            Удалить все медиа
          </button>
        )}
      </div>

      <dialog
        ref={deleteDialogRef}
        aria-labelledby="delete-media-title"
        aria-describedby="delete-media-description"
        onClose={() => setPendingDeletion(null)}
        onCancel={() => setPendingDeletion(null)}
        onClick={event => { if (event.target === event.currentTarget) setPendingDeletion(null); }}
        className="w-[min(24rem,calc(100vw-2rem))] rounded-xl border border-slate-200 bg-white p-0 text-slate-900 shadow-2xl backdrop:bg-slate-900/60"
      >
        {pendingDeletion && (
          <div className="p-5">
            <div className="flex items-start justify-between gap-3">
              <h2 id="delete-media-title" className="text-sm font-bold">
                {pendingDeletion.kind === 'all' ? 'Удалить все медиа?' : 'Удалить файл?'}
              </h2>
              <button
                type="button"
                onClick={() => setPendingDeletion(null)}
                aria-label="Закрыть окно удаления"
                className="rounded-md p-1 text-slate-500 hover:bg-slate-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                <X className="h-4 w-4" aria-hidden="true" />
              </button>
            </div>
            <p id="delete-media-description" className="mt-2 text-xs leading-relaxed text-slate-600">
              {pendingDeletion.kind === 'all'
                ? `Будут удалены все изображения (${images.length}) из браузера и текущей сессии.`
                : <>Изображение <strong>«{pendingDeletion.name}»</strong> будет удалено из браузера и текущей сессии.</>}
              {' '}Ссылки на изображения в тексте останутся. Чтобы восстановить файлы, их понадобится загрузить заново.
            </p>
            {pendingDeletion.kind === 'all' && (
              <>
                <ul className="mt-3 max-h-28 space-y-1 overflow-y-auto rounded-lg bg-slate-50 p-2 text-xs text-slate-700">
                  {images.map(img => <li key={img.name} className="truncate" title={img.name}>{img.name}</li>)}
                </ul>
                <label className="mt-4 flex cursor-pointer items-start gap-2 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    checked={acknowledged}
                    onChange={event => setAcknowledged(event.target.checked)}
                    className="mt-0.5 accent-red-600"
                  />
                  <span>Понимаю, что все изображения придётся загрузить заново</span>
                </label>
              </>
            )}
            <div className="mt-5 flex justify-end gap-2">
              <button
                ref={cancelDeleteRef}
                type="button"
                onClick={() => setPendingDeletion(null)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={confirmDeletion}
                disabled={images.length === 0 || (pendingDeletion.kind === 'all' ? !acknowledged : !images.some(img => img.name === pendingDeletion.name))}
                className="rounded-lg bg-red-600 px-3 py-2 text-xs font-semibold text-white hover:bg-red-700 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-red-700"
              >
                {pendingDeletion.kind === 'all' ? 'Удалить все медиа' : 'Удалить файл'}
              </button>
            </div>
          </div>
        )}
      </dialog>
    </div>
  );
};
