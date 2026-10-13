import React, { useState, useEffect, useRef } from 'react';
import { 
  Images, Upload, Plus, Trash2, CheckCircle2, Clock, 
  Copy, Check, FileImage
} from 'lucide-react';

interface ImageGalleryProps {
  images: File[];
  onImagesChange: (imgs: File[]) => void;
  onInsertImage: (fileName: string, altText?: string) => void;
  markdownContent: string;
  onSwitchToEditor?: () => void;
}

export const ImageGallery: React.FC<ImageGalleryProps> = ({
  images,
  onImagesChange,
  onInsertImage,
  markdownContent,
  onSwitchToEditor
}) => {
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const [copiedName, setCopiedName] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    const urls: string[] = [];
    const map: Record<string, string> = {};

    images.forEach(img => {
      try {
        const url = URL.createObjectURL(img);
        urls.push(url);
        map[img.name] = url;
      } catch {
        // ignore
      }
    });

    setPreviews(map);

    return () => {
      urls.forEach(url => {
        try {
          URL.revokeObjectURL(url);
        } catch {}
      });
    };
  }, [images]);

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    const newFiles: File[] = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      if (file.type.startsWith('image/')) {
        // Do not add duplicate filenames.
        if (!images.some(existing => existing.name === file.name)) {
          newFiles.push(file);
        }
      }
    }
    if (newFiles.length > 0) {
      onImagesChange([...images, ...newFiles]);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleFiles(e.dataTransfer.files);
  };

  const removeImage = (idx: number) => {
    onImagesChange(images.filter((_, i) => i !== idx));
  };

  const copyMarkdownCode = (filename: string) => {
    const code = `![Иллюстрация](${filename})`;
    navigator.clipboard.writeText(code);
    setCopiedName(filename);
    setTimeout(() => setCopiedName(null), 2000);
  };

  // Check whether the report references the filename.
  const isImageInserted = (filename: string): boolean => {
    if (!markdownContent) return false;
    const raw = markdownContent;
    return raw.includes(`(${filename})`) || 
           raw.includes(`(${encodeURIComponent(filename)})`) ||
           raw.includes(filename);
  };

  const formatSize = (bytes: number): string => {
    if (bytes < 1024) return `${bytes} Б`;
    if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} КБ`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} МБ`;
  };

  // Derive a readable caption from the filename.
  const suggestCaption = (filename: string): string => {
    const withoutExt = filename.replace(/\.[^/.]+$/, "");
    // Replace generic work/screenshot filenames with a descriptive placeholder.
    if (/^[a-zA-Z0-9_\s()-]+$/.test(withoutExt)) {
      return `Иллюстрация (${withoutExt})`;
    }
    return withoutExt;
  };

  const insertedCount = images.filter(img => isImageInserted(img.name)).length;
  const pendingCount = images.length - insertedCount;

  // Append all images not yet referenced by the report.
  const handleInsertAllPending = () => {
    const uninserted = images.filter(img => !isImageInserted(img.name));
    uninserted.forEach(img => {
      onInsertImage(img.name, suggestCaption(img.name));
    });
  };

  return (
    <div className="rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden flex flex-col h-full flex-1 min-h-0">
      {/* Image gallery header. */}
      <div className="flex flex-wrap items-center justify-between border-b border-slate-200 bg-slate-50/90 px-4 py-2.5 gap-2 shrink-0">
        <div className="flex items-center gap-2">
          <div className="rounded-lg bg-purple-100 p-1 text-purple-700">
            <Images className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-bold text-slate-800">Пул скриншотов и иллюстраций</span>
              <span className="rounded-full bg-slate-200/80 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                {images.length} фото
              </span>
              {insertedCount > 0 && (
                <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                  {insertedCount} в тексте
                </span>
              )}
              {pendingCount > 0 && (
                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                  {pendingCount} в очереди
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {onSwitchToEditor && (
            <button
              type="button"
              onClick={onSwitchToEditor}
              className="px-2.5 py-1 text-xs font-semibold text-slate-600 hover:text-blue-700 hover:bg-slate-100 rounded-lg transition-colors"
              title="Перейти обратно к редактированию текста"
            >
              ← К тексту
            </button>
          )}

          {pendingCount > 1 && (
            <button
              type="button"
              onClick={handleInsertAllPending}
              className="flex items-center gap-1 rounded-lg border border-purple-200 bg-purple-50 px-2.5 py-1 text-[11px] font-bold text-purple-700 hover:bg-purple-100 transition-colors shadow-sm"
              title="Вставить все невставленные рисунки по порядку"
            >
              <Copy className="h-3 w-3" /> Вставить все в текст
            </button>
          )}

          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept="image/*"
            onChange={e => {
              handleFiles(e.target.files);
              e.target.value = '';
            }}
            className="hidden"
          />

          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1.5 rounded-lg bg-purple-600 px-3 py-1 text-xs font-bold text-white hover:bg-purple-700 shadow-sm active:scale-95 transition-all"
          >
            <Upload className="h-3.5 w-3.5" /> Загрузить фото
          </button>
        </div>
      </div>

      {/* Drop zone or internally scrolling gallery. */}
      <div 
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`flex-1 overflow-y-auto p-3 transition-colors ${
          isDragging ? 'bg-purple-50/70 border-2 border-dashed border-purple-400' : 'bg-slate-50/30'
        }`}
      >
        {images.length === 0 ? (
          /* Empty-state drop zone. */
          <div 
            onClick={() => fileInputRef.current?.click()}
            className="flex flex-col items-center justify-center p-6 border-2 border-dashed border-slate-300 rounded-xl cursor-pointer hover:border-purple-400 hover:bg-purple-50/30 transition-all text-center group"
          >
            <div className="rounded-full bg-purple-100/70 p-3 text-purple-600 group-hover:scale-110 transition-transform mb-2">
              <Upload className="h-6 w-6" />
            </div>
            <p className="text-xs font-bold text-slate-700 mb-0.5">
              Загрузите пачку скриншотов сюда (выберите сразу несколько файлов или перетащите)
            </p>
            <p className="text-[11px] text-slate-500">
              Поддерживаются PNG, JPG, WebP. Вы сможете вставлять их по одному клику в нужные места отчета.
            </p>
          </div>
        ) : (
          /* Image cards. */
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2.5 max-h-56 overflow-y-auto pr-1">
            {images.map((img, idx) => {
              const inserted = isImageInserted(img.name);
              const previewUrl = previews[img.name];

              return (
                <div
                  key={idx}
                  className={`group relative flex flex-col rounded-lg border bg-white p-1.5 shadow-sm transition-all hover:shadow-md ${
                    inserted
                      ? 'border-emerald-200 ring-1 ring-emerald-400/30'
                      : 'border-slate-200 hover:border-purple-300'
                  }`}
                >
                  {/* Image preview. */}
                  <div className="relative h-20 w-full overflow-hidden rounded bg-slate-100 flex items-center justify-center border border-slate-100">
                    {previewUrl ? (
                      <img
                        src={previewUrl}
                        alt={img.name}
                        className="h-full w-full object-contain"
                      />
                    ) : (
                      <FileImage className="h-8 w-8 text-slate-400" />
                    )}

                    {/* Status badge. */}
                    <div className="absolute top-1 left-1">
                      {inserted ? (
                        <span className="flex items-center gap-0.5 rounded bg-emerald-600/90 backdrop-blur-sm px-1 py-0.5 text-[9px] font-bold text-white shadow-sm">
                          <CheckCircle2 className="h-2.5 w-2.5" /> Вставлен
                        </span>
                      ) : (
                        <span className="flex items-center gap-0.5 rounded bg-amber-500/90 backdrop-blur-sm px-1 py-0.5 text-[9px] font-bold text-white shadow-sm">
                          <Clock className="h-2.5 w-2.5" /> В очереди
                        </span>
                      )}
                    </div>

                    {/* Delete button. */}
                    <button
                      type="button"
                      onClick={() => removeImage(idx)}
                      className="absolute top-1 right-1 rounded bg-black/60 p-1 text-white opacity-0 group-hover:opacity-100 hover:bg-red-600 transition-all"
                      title="Удалить из пула"
                    >
                      <Trash2 className="h-3 w-3" />
                    </button>
                  </div>

                  {/* Metadata. */}
                  <div className="mt-1 flex flex-col justify-between flex-1">
                    <div className="truncate text-[10.5px] font-medium text-slate-800" title={img.name}>
                      {img.name}
                    </div>
                    <div className="text-[9.5px] text-slate-400 mb-1.5">
                      {formatSize(img.size)}
                    </div>

                    {/* Actions. */}
                    <div className="flex items-center gap-1 mt-auto">
                      <button
                        type="button"
                        onClick={() => onInsertImage(img.name, suggestCaption(img.name))}
                        className={`flex-1 flex items-center justify-center gap-0.5 rounded py-1 text-[10.5px] font-bold transition-all ${
                          inserted
                            ? 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                            : 'bg-purple-600 text-white hover:bg-purple-700 shadow-sm active:scale-95'
                        }`}
                        title="Вставить этот рисунок в текущую позицию курсора в тексте"
                      >
                        <Plus className="h-3 w-3" /> Вставить
                      </button>

                      <button
                        type="button"
                        onClick={() => copyMarkdownCode(img.name)}
                        className="rounded bg-slate-100 p-1 text-slate-600 hover:bg-slate-200 hover:text-slate-900"
                        title="Скопировать Markdown-код рисунка"
                      >
                        {copiedName === img.name ? (
                          <Check className="h-3 w-3 text-emerald-600" />
                        ) : (
                          <Copy className="h-3 w-3" />
                        )}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
