import React, { useState, useEffect, useLayoutEffect, useRef, useMemo, useCallback } from 'react';
import { Header } from './components/Header';
import { MetadataForm } from './components/MetadataForm';
import { MarkdownEditor } from './components/MarkdownEditor';
import { DocumentPreview } from './components/DocumentPreview';
import { TableModal } from './components/TableModal';
import { ExternalVerifyModal } from './components/ExternalVerifyModal';
import { AiPromptModal } from './components/AiPromptModal';
import { McpModal } from './components/McpModal';
import { ReportGuideModal } from './components/ReportGuideModal';
import { ReportMetadata } from './types';
import { EditorSelection } from './services/editorInsertion';
import { extractMarkdownImageSources } from './services/markdown';
import { isExternalImageRef, resolveImageName } from './services/imageRefs';
import { generateDocument, autofixMarkdown, getRuntimeCapabilities, getVersionInfo, type VersionInfo } from './services/api';
import { 
  initSession, 
  syncSessionToServer, 
  subscribeToSessionEvents,
  uploadSessionImages,
  getSessionImages,
  deleteSessionImage,
  fetchSessionImageAsFile,
  clearStoredToken,
  getClientId,
  serializeMetadata,
  metadataUpdateMessage,
  applyContentPatches,
  buildContentPatches,
  type SessionInitResponse,
  type ContentPatch,
} from './services/session';
import { recoverSessionImages } from './services/imageRecovery';
import { canonicalImageName, deleteStoredImage, deleteStoredImageByName, deleteStoredImageFile, getStoredImages, saveStoredImage } from './services/imageStore';
import { 
  getGlobalProfile, 
  getSubjectPresets, 
  saveSubjectPresets, 
  getActiveSubjectId, 
  setActiveSubjectId as saveActiveSubjectId, 
  createNewSubjectPreset,
  normalizeLogoMode,
  createProfile,
  serializeProfile,
  parseProfile,
  applyProfile,
  profileFilename,
  PROFILE_MAX_BYTES,
  SubjectPreset 
} from './services/profiles';
import { FileEdit, Settings2, Plus, BookOpen, Eye } from 'lucide-react';

const REPORT_META_KEY = 'report_meta';
const REPORT_CONTENT_KEY = 'report_content';
type RemoteConflict = {
  content?: { content: string; revision: string };
  meta?: { meta: Partial<ReportMetadata>; revision: string };
};

// Missing image attachments become DOCX placeholders; warn before download.
// Ignore fenced code and external http/data/blob URLs.
const findMissingImageRefs = (text: string, files: File[]): string[] => {
  if (!text) return [];
  const knownNames = files.map(file => file.name);
  const missing: string[] = [];
  const seen = new Set<string>();
  for (const image of extractMarkdownImageSources(text)) {
    const src = image.src.trim().replace(/^<|>$/g, '');
    if (!src || seen.has(src)) continue;
    seen.add(src);
    if (isExternalImageRef(src)) {
      continue;
    }
    if (!resolveImageName(src, knownNames)) {
      missing.push(src);
    }
  }
  return missing;
};

const findUnsupportedImageRefs = (text: string): string[] => [...new Set(
  extractMarkdownImageSources(text)
    .map(image => image.src.trim().replace(/^<|>$/g, ''))
    .filter(isExternalImageRef),
)];

// Confirm download with missing images; return true to proceed.
const confirmMissingImages = (missing: string[], unsupported: string[] = []): boolean => {
  if (missing.length === 0 && unsupported.length === 0) return true;
  const parts: string[] = [];
  if (missing.length > 0) {
    const shown = missing.slice(0, 5).join(', ');
    const rest = missing.length > 5 ? ` и ещё ${missing.length - 5}` : '';
    parts.push(`не прикреплены (${shown}${rest})`);
  }
  if (unsupported.length > 0) {
    parts.push(`не поддерживаются при сборке DOCX/PDF (${unsupported.slice(0, 5).join(', ')})`);
  }
  return window.confirm(
    `В тексте есть изображения, которые ${parts.join(' и ')}. ` +
    `В документ вместо них попадут плейсхолдеры «[ Иллюстрация ]». Продолжить скачивание?`
  );
};

const readStoredValue = (key: string): string | null => {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  Boolean(value) && typeof value === 'object' && !Array.isArray(value);

const isStudentEntry = (value: unknown): value is { fio: string; group: string } =>
  isRecord(value) && typeof value.fio === 'string' && typeof value.group === 'string';

const isTeacherEntry = (value: unknown): value is { fio: string; role: string } =>
  isRecord(value) && typeof value.fio === 'string' && typeof value.role === 'string';

const fileToBase64 = async (file: File): Promise<string> => {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  const chunkSize = 0x8000;
  for (let start = 0; start < bytes.length; start += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(start, start + chunkSize));
  }
  return btoa(binary);
};

const base64ToFile = (data: string, filename: string, type: string, lastModified: number): File => {
  const binary = atob(data);
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0));
  return new File([bytes], filename, { type, lastModified });
};

const initialGlobal = getGlobalProfile();
const initialPresets = getSubjectPresets();
const initialActiveId = getActiveSubjectId();
const initialSubject = initialPresets.find(p => p.id === initialActiveId);

const DEFAULT_META: ReportMetadata = {
  university: initialGlobal.university || "",
  ministry: initialGlobal.ministry || "МИНИСТЕРСТВО НАУКИ И ВЫСШЕГО ОБРАЗОВАНИЯ РОССИЙСКОЙ ФЕДЕРАЦИИ",
  logo_mode: normalizeLogoMode(initialGlobal.logo_mode),
  custom_logo: initialGlobal.custom_logo,
  city: initialGlobal.city || "",
  institute: initialSubject?.institute || "",
  department: initialSubject?.department || "",
  doc_type: "ОТЧЕТ",
  work_type: "о выполнении лабораторной работы",
  work_number: 1,
  work_theme: "",
  discipline: initialSubject?.name || "",
  students: initialGlobal.default_student?.fio ? [initialGlobal.default_student] : [{ fio: "", group: "" }],
  teachers: initialSubject?.teachers && initialSubject.teachers.length > 0 
    ? initialSubject.teachers 
    : [{ fio: "", role: "ст. преп." }],
  year: new Date().getFullYear(),
  heading_alignment: "center",
  page_numbering: "center",
  page_break_before_h1: false,
  hide_captions: false,
  custom_instructions: initialSubject?.custom_instructions || "",
  prompt_latex: true,
  latex_mode: "omml"
};

const getWorkPrefix = (workType?: string): string => {
  const wt = (workType || '').toLowerCase();
  if (wt.includes('практическ')) return 'ПР';
  if (wt.includes('расчетно-графическ') || wt.includes('ргр')) return 'РГР';
  if (wt.includes('курсов') && wt.includes('проект')) return 'КП';
  if (wt.includes('курсов')) return 'КР';
  if (wt.includes('научно-исследовательск') || wt.includes('нир')) return 'НИР';
  if (wt.includes('производственн') && wt.includes('практик')) return 'ПП';
  if (wt.includes('учебн') && wt.includes('практик')) return 'УП';
  if (wt.includes('преддипломн') && wt.includes('практик')) return 'ПДП';
  if (wt.includes('контрольн')) return 'КСР';
  if (wt.includes('практик')) return 'Практика';
  if (wt.includes('лабораторн')) return 'ЛР';
  return 'Работа';
};

export const App: React.FC = () => {
  // Restore localStorage state using neutral keys with legacy compatibility.
  const [meta, setMeta] = useState<ReportMetadata>(() => {
    const saved = readStoredValue(REPORT_META_KEY);
    if (saved) {
      try {
        const parsed = JSON.parse(saved);
        return {
          ...DEFAULT_META,
          ...parsed,
          logo_mode: normalizeLogoMode(parsed.logo_mode),
          students: Array.isArray(parsed.students) && parsed.students.length > 0 ? parsed.students : DEFAULT_META.students,
          teachers: Array.isArray(parsed.teachers) && parsed.teachers.length > 0 ? parsed.teachers : DEFAULT_META.teachers,
          heading_alignment: parsed.heading_alignment === 'left' ? 'left' : 'center',
          page_numbering: (parsed.page_numbering === 'right' || parsed.page_numbering === 'none') ? parsed.page_numbering : 'center',
          page_break_before_h1: parsed.page_break_before_h1 ?? false,
          hide_captions: parsed.hide_captions ?? false,
          custom_instructions: parsed.custom_instructions || "",
          prompt_latex: parsed.prompt_latex ?? true,
          latex_mode: parsed.latex_mode === 'unicode' ? 'unicode' : 'omml'
        };
      } catch {}
    }
    return DEFAULT_META;
  });

  const [content, setContent] = useState<string>(() => {
    return readStoredValue(REPORT_CONTENT_KEY) || '';
  });

  const [images, setImages] = useState<File[]>([]);
  const imageRevisionRef = useRef<string | undefined>(undefined);
  const [failedImageUploads, setFailedImageUploads] = useState<File[]>([]);
  const [retryingImageUploads, setRetryingImageUploads] = useState(false);
  const [localImageError, setLocalImageError] = useState<string | null>(null);
  const mediaQueueRef = useRef<Promise<void>>(Promise.resolve());
  const imagesRef = useRef(images);
  const initSessionPromiseRef = useRef<Promise<void> | null>(null);
  const [leftView, setLeftView] = useState<'editor' | 'settings'>('editor');
  const [mobileTab, setMobileTab] = useState<'editor' | 'preview'>('editor');
  const [subjectPresets, setSubjectPresets] = useState<SubjectPreset[]>(() => getSubjectPresets());
  const [activeSubjectId, setActiveSubjectIdState] = useState<string>(() => getActiveSubjectId());
  const [isGenerating, setIsGenerating] = useState(false);
  const [pdfExportEnabled, setPdfExportEnabled] = useState(false);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [updateDismissed, setUpdateDismissed] = useState(false);
  const [isTableModalOpen, setIsTableModalOpen] = useState(false);
  const [isVerifyModalOpen, setIsVerifyModalOpen] = useState(false);
  const [isAiModalOpen, setIsAiModalOpen] = useState(false);
  const [isMcpModalOpen, setIsMcpModalOpen] = useState(false);
  const [isGuideModalOpen, setIsGuideModalOpen] = useState(false);
  const [isSubjectModalOpen, setIsSubjectModalOpen] = useState(false);
  const [subjectModalMode, setSubjectModalMode] = useState<'create' | 'delete'>('create');
  const [subjectModalName, setSubjectModalName] = useState('');
  const [subjectModalTargetId, setSubjectModalTargetId] = useState('');
  const [sessionToken, setSessionToken] = useState<string>('');
  const activeTokenRef = useRef('');
  const sessionGenerationRef = useRef(0);
  const clientIdRef = useRef(getClientId());
  const hadStoredMetaRef = useRef(readStoredValue(REPORT_META_KEY) !== null);
  const [syncConflict, setSyncConflict] = useState<RemoteConflict | null>(null);
  const [syncError, setSyncError] = useState(false);
  const contentRef = useRef(content);
  const metaRef = useRef(meta);
  const acknowledgedRef = useRef<{ content: string; revision: string; meta: string; metaRevision: string } | null>(null);
  const conflictRef = useRef<RemoteConflict | null>(null);
  const inFlightRef = useRef<{ content?: string; meta?: string } | null>(null);
  const syncQueueRef = useRef<Promise<void>>(Promise.resolve());
  const syncRetryTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const syncRetryAttemptRef = useRef(0);
  const localStorageTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useLayoutEffect(() => {
    contentRef.current = content;
    metaRef.current = meta;
    imagesRef.current = images;
  }, [content, meta, images]);
  const persistLocalState = useCallback(() => {
    try {
      localStorage.setItem(REPORT_META_KEY, JSON.stringify(metaRef.current));
      localStorage.setItem(REPORT_CONTENT_KEY, contentRef.current);
    } catch (error) {
      console.warn("Failed to save report state to localStorage:", error);
    }
  }, []);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const toastTimerRef = React.useRef<any>(null);
  const insertIntoEditorRef = useRef<((text: string) => void) | null>(null);
  const editorSelectionRef = useRef<EditorSelection>({ start: 0, end: 0 });
  const pendingEditorInsertRef = useRef<string | null>(null);
  const registerEditorInsert = useCallback((insert: ((text: string) => void) | null) => {
    insertIntoEditorRef.current = insert;
    const pending = pendingEditorInsertRef.current;
    if (insert && pending !== null) {
      pendingEditorInsertRef.current = null;
      insert(pending);
    }
  }, []);

  const workPrefix = useMemo(() => getWorkPrefix(meta.work_type), [meta.work_type]);
  const workTypeShort = useMemo(() => `${workPrefix} №`, [workPrefix]);

  // Skip last_work_number persistence when the number is suggested automatically.
  const skipLastNumPersist = useRef(false);

  const handleSwitchSubject = (id: string) => {
    setActiveSubjectIdState(id);
    saveActiveSubjectId(id);
    if (!id) return;
    const presets = getSubjectPresets();
    const found = presets.find(p => p.id === id);
    if (found) {
      if (found.last_work_number) skipLastNumPersist.current = true;
      setMeta(prev => ({
        ...prev,
        discipline: found.name,
        institute: found.institute || prev.institute,
        department: found.department || prev.department,
        teachers: found.teachers && found.teachers.length > 0 ? found.teachers : prev.teachers,
        custom_instructions: found.custom_instructions || '',
        work_number: found.last_work_number ? found.last_work_number + 1 : prev.work_number
      }));
      showToast(`Выбран шаблон «${found.name}»`);
    }
  };

  // Remember the last used number in the active preset to suggest the next one.
  // Automatic suggestions during preset switching must not advance the counter.
  const persistLastNumber = (num: number) => {
    if (!activeSubjectId || !(num > 0)) return;
    const presets = getSubjectPresets();
    const found = presets.find(p => p.id === activeSubjectId);
    if (found && found.last_work_number !== num) {
      const updated = presets.map(p => p.id === activeSubjectId ? { ...p, last_work_number: num } : p);
      setSubjectPresets(updated);
      saveSubjectPresets(updated);
    }
  };
  useEffect(() => {
    if (skipLastNumPersist.current) {
      skipLastNumPersist.current = false;
      return;
    }
    persistLastNumber(Number(meta.work_number) || 0);
  }, [meta.work_number, activeSubjectId]);

  const handleCreateNewSubject = (name: string) => {
    const trimmed = name.trim();
    if (!trimmed) return;
    const newPreset = createNewSubjectPreset(trimmed);
    newPreset.institute = meta.institute;
    newPreset.department = meta.department;
    newPreset.teachers = meta.teachers;
    newPreset.custom_instructions = meta.custom_instructions;
    newPreset.last_work_number = Number(meta.work_number) || undefined;
    const updated = [...subjectPresets, newPreset];
    setSubjectPresets(updated);
    saveSubjectPresets(updated);
    handleSwitchSubject(newPreset.id);
  };

  const handleDeleteSubject = (id: string) => {
    const found = subjectPresets.find(p => p.id === id);
    const name = found ? found.name : "дисциплина";

    const updated = subjectPresets.filter(p => p.id !== id);
    setSubjectPresets(updated);
    saveSubjectPresets(updated);
    
    if (activeSubjectId === id) {
      const nextId = updated[0]?.id || "";
      setActiveSubjectIdState(nextId);
      saveActiveSubjectId(nextId);
      if (nextId) {
        handleSwitchSubject(nextId);
      };
    }
    showToast(`Шаблон «${name}» удалён`);
  };

  // Debounce synchronous storage writes so typing does not block on serialization.
  useEffect(() => {
    if (localStorageTimerRef.current) clearTimeout(localStorageTimerRef.current);
    localStorageTimerRef.current = setTimeout(persistLocalState, 300);
    return () => {
      if (localStorageTimerRef.current) {
        clearTimeout(localStorageTimerRef.current);
        localStorageTimerRef.current = null;
      }
    };
  }, [content, meta, persistLocalState]);

  useEffect(() => {
    window.addEventListener('pagehide', persistLocalState);
    return () => window.removeEventListener('pagehide', persistLocalState);
  }, [persistLocalState]);

  useEffect(() => {
    let active = true;
    getVersionInfo()
      .then(info => {
        if (active) setVersionInfo(info);
      })
      .catch(() => {
        // Update checks are optional and must not affect report editing.
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    getRuntimeCapabilities()
      .then(capabilities => {
        if (active) setPdfExportEnabled(capabilities.pdf_export);
      })
      .catch(() => {
        if (active) setPdfExportEnabled(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
      if (syncRetryTimerRef.current) clearTimeout(syncRetryTimerRef.current);
      if (localStorageTimerRef.current) clearTimeout(localStorageTimerRef.current);
    };
  }, []);

  const queueMediaOperation = (operation: () => Promise<void>): Promise<void> => {
    const result = mediaQueueRef.current.then(operation);
    mediaQueueRef.current = result.catch(() => {});
    return result;
  };

  const restoreSessionImages = (
    token: string,
    manifest?: { images: NonNullable<SessionInitResponse['images']>; deleted: string[]; image_revision?: string },
  ): Promise<void> => queueMediaOperation(async () => {
    if (token !== activeTokenRef.current) return;
    for (const file of imagesRef.current) await saveStoredImage(file);
    const before = await getStoredImages();
    if (token !== activeTokenRef.current) return;
    setImages(prev => {
      const existing = new Set(before.map(image => image.filename));
      return [...before.map(image => image.file), ...prev.filter(file => !existing.has(file.name))];
    });
    const server = manifest || await getSessionImages(token);
    if (server.image_revision) imageRevisionRef.current = server.image_revision;
    await recoverSessionImages(token, server.images, server.deleted);
    if (token !== activeTokenRef.current) return;
    const after = await getStoredImages();
    const oldNames = new Set(before.map(image => image.filename));
    const currentNames = new Set(after.map(image => image.filename));
    setImages(prev => [
      ...after.map(image => image.file),
      ...prev.filter(file => !oldNames.has(file.name) && !currentNames.has(file.name)),
    ]);
    setFailedImageUploads([]);
    setLocalImageError(null);
  }).catch(error => {
    console.warn('Failed to restore images:', error);
    setLocalImageError(error instanceof Error ? error.message : 'Не удалось восстановить изображения');
  });

  const uploadImagesToSession = (files: File[]): Promise<void> => {
    if (files.length === 0) {
      setFailedImageUploads([]);
      return Promise.resolve();
    }
    return queueMediaOperation(async () => {
      for (const file of files) await saveStoredImage(file);
      const token = activeTokenRef.current;
      if (!token) return;
      const uploaded = await uploadSessionImages(token, files);
      const uploadedRevision = uploaded.find(item => item.image_revision)?.image_revision;
      if (uploadedRevision) imageRevisionRef.current = uploadedRevision;
      const renamed = uploaded.map((item, index) => new File([files[index]], item.filename, {
        type: files[index].type, lastModified: files[index].lastModified,
      }));
      for (let index = 0; index < renamed.length; index += 1) {
        await saveStoredImage(renamed[index]);
        if (renamed[index].name !== files[index].name) await deleteStoredImage(files[index].name);
      }
      if (token === activeTokenRef.current) {
        setFailedImageUploads(prev => prev.filter(file => !files.includes(file)));
        setImages(prev => {
          const remaining = prev.filter(file => !files.includes(file));
          return [...remaining, ...renamed.filter(file => !remaining.some(other => other.name === file.name))];
        });
      }
    }).catch(error => {
      console.warn('Failed to upload images to the session:', error);
      setFailedImageUploads(prev => [...prev, ...files.filter(file => !prev.includes(file))]);
      setLocalImageError(error instanceof Error ? error.message : 'Не удалось сохранить изображения');
    });
  };

  const handleImagesChange = (newImages: File[]) => {
    const addedFiles = newImages.filter(f => !images.some(old => old.name === f.name));
    const removedFiles = images.filter(old => !newImages.some(f => f.name === old.name));

    setImages(newImages);
    setFailedImageUploads(prev => prev.filter(file => !removedFiles.includes(file)));

    if (addedFiles.length > 0) void uploadImagesToSession(addedFiles);
    removedFiles.forEach(file => {
      void queueMediaOperation(async () => {
        if (sessionToken) {
          const result = await deleteSessionImage(sessionToken, file.name, imageRevisionRef.current);
          if (result.image_revision) imageRevisionRef.current = result.image_revision;
        }
        await deleteStoredImageFile(file);
        setImages(prev => prev.filter(item => item.name !== file.name));
        setMeta(prev => {
          if (!prev.image_layouts) return prev;
          const remaining = Object.fromEntries(
            Object.entries(prev.image_layouts).filter(([name]) => canonicalImageName(name) !== canonicalImageName(file.name))
          );
          return Object.keys(remaining).length === Object.keys(prev.image_layouts).length
            ? prev
            : { ...prev, image_layouts: remaining };
        });
      }).catch(error => {
        console.warn('Failed to delete image:', error);
        setImages(prev => prev.some(item => item.name === file.name) ? prev : [...prev, file]);
        setLocalImageError(`Не удалось удалить «${file.name}»: ${error instanceof Error ? error.message : 'ошибка сохранения'}`);
      });
    });
  };

  const showRemoteConflict = (remote: RemoteConflict) => {
    const next = { ...conflictRef.current, ...remote };
    conflictRef.current = next;
    setSyncConflict(next);
    setSyncError(false);
  };

  const scheduleSyncRetry = (token: string, retryAfter?: number) => {
    if (token !== activeTokenRef.current || syncRetryTimerRef.current) return;
    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      setSyncError(true);
      return;
    }
    const attempt = syncRetryAttemptRef.current++;
    const exponential = Math.min(30_000, 1_000 * (2 ** Math.min(attempt, 5)));
    const jitter = Math.floor(Math.random() * Math.max(250, exponential * 0.25));
    const delay = Math.max(retryAfter || 0, exponential + jitter);
    syncRetryTimerRef.current = setTimeout(() => {
      syncRetryTimerRef.current = null;
      queueSessionSync(token);
    }, delay);
    setSyncError(true);
  };

  const queueSessionSync = (token: string) => {
    syncQueueRef.current = syncQueueRef.current.then(async () => {
      if (token !== activeTokenRef.current) return;
      if (typeof navigator !== 'undefined' && !navigator.onLine) {
        setSyncError(true);
        return;
      }
      const base = acknowledgedRef.current;
      if (!base || conflictRef.current) return;
      const operationGeneration = sessionGenerationRef.current;
      const localContent = contentRef.current;
      const localMeta = metaRef.current;
      const localMetaJson = serializeMetadata(localMeta);
      const payload: {
        content?: string;
        content_patches?: ContentPatch[];
        meta?: ReportMetadata;
        expected_revision?: string;
        expected_meta_revision?: string;
      } = {};
      if (localContent !== base.content) {
        const patches = buildContentPatches(base.content, localContent);
        const patchBytes = new TextEncoder().encode(JSON.stringify(patches)).byteLength;
        const contentBytes = new TextEncoder().encode(localContent).byteLength;
        if (patchBytes < contentBytes) payload.content_patches = patches;
        else payload.content = localContent;
        payload.expected_revision = base.revision;
      }
      if (localMetaJson !== base.meta) {
        payload.meta = localMeta;
        payload.expected_meta_revision = base.metaRevision;
      }
      if (!('content' in payload) && !('content_patches' in payload) && !('meta' in payload)) {
        setSyncError(false);
        return;
      }
      inFlightRef.current = { content: localContent, meta: payload.meta ? localMetaJson : undefined };
      try {
        const result = await syncSessionToServer(token, payload);
        if (token !== activeTokenRef.current || operationGeneration !== sessionGenerationRef.current) return;
        if (result.status === 'conflict') {
          if (result.conflict_type === 'content') {
            showRemoteConflict({ content: { content: result.content, revision: result.revision } });
          } else {
            showRemoteConflict({ meta: { meta: result.meta, revision: result.meta_revision } });
          }
          return;
        }
        const latest = acknowledgedRef.current;
        if (latest && !conflictRef.current) {
          // The request's SSE event can precede its HTTP response. Do not
          // replace a newer revision with an older acknowledgement.
          const contentWasSent = payload.content !== undefined || payload.content_patches !== undefined;
          acknowledgedRef.current = {
            content: contentWasSent && latest.revision === base.revision ? localContent : latest.content,
            revision: contentWasSent && latest.revision === base.revision ? result.revision : latest.revision,
            meta: payload.meta !== undefined && latest.metaRevision === base.metaRevision ? localMetaJson : latest.meta,
            metaRevision: payload.meta !== undefined && latest.metaRevision === base.metaRevision ? result.meta_revision : latest.metaRevision,
          };
        }
        syncRetryAttemptRef.current = 0;
        if (syncRetryTimerRef.current) {
          clearTimeout(syncRetryTimerRef.current);
          syncRetryTimerRef.current = null;
        }
        setSyncError(false);
      } catch (error) {
        console.warn('Failed to synchronize report:', error);
        scheduleSyncRetry(token, (error as { retryAfterMs?: number }).retryAfterMs);
      } finally {
        inFlightRef.current = null;
      }
    });
  };

  // Browser originals remain available when the server is unreachable.
  useEffect(() => {
    let active = true;
    void queueMediaOperation(async () => {
      const local = await getStoredImages();
      if (active) setImages(prev => {
        const storedNames = new Set(local.map(image => image.filename));
        return [...local.map(image => image.file), ...prev.filter(file => !storedNames.has(file.name))];
      });
    }).catch(error => {
      if (active) setLocalImageError(error instanceof Error ? error.message : 'Не удалось прочитать локальные изображения');
    });
    return () => { active = false; };
  }, []);

  const initializeBrowserSession = (): Promise<void> => {
    if (initSessionPromiseRef.current) return initSessionPromiseRef.current;
    const pending = initSession()
      .then(sess => {
        sessionGenerationRef.current += 1;
        activeTokenRef.current = sess.token;
        imageRevisionRef.current = sess.image_revision;
        const restoredMeta = { ...DEFAULT_META, ...(sess.meta || {}) };
        acknowledgedRef.current = {
          content: sess.content, revision: sess.revision,
          meta: serializeMetadata(restoredMeta), metaRevision: sess.meta_revision,
        };
        setSessionToken(sess.token);

        // Do not guess which of two distinct nonempty versions is newer.
        if (sess.content && contentRef.current && sess.content !== contentRef.current) {
          showRemoteConflict({ content: { content: sess.content, revision: sess.revision } });
        } else if (sess.content && !contentRef.current) {
          contentRef.current = sess.content;
          setContent(sess.content);
        }
        if (Object.keys(sess.meta || {}).length > 0) {
          if (hadStoredMetaRef.current && serializeMetadata(restoredMeta) !== serializeMetadata(metaRef.current)) {
            showRemoteConflict({ meta: { meta: sess.meta, revision: sess.meta_revision } });
          } else if (!hadStoredMetaRef.current) {
            metaRef.current = restoredMeta;
            setMeta(restoredMeta);
          }
        }

        void restoreSessionImages(sess.token, {
          images: sess.images || [],
          deleted: sess.deleted || [],
          image_revision: sess.image_revision,
        });
      })
      .catch(err => {
        console.warn("Session init error:", err);
        setLocalImageError('Сервер недоступен. Локальные изображения остаются в браузере.');
      }).finally(() => {
        initSessionPromiseRef.current = null;
      });
    initSessionPromiseRef.current = pending;
    return pending;
  };

  const applyRemoteSessionSnapshot = (sess: SessionInitResponse): void => {
    const base = acknowledgedRef.current;
    if (!base) return;

    const localContent = contentRef.current;
    const localContentDirty = localContent !== base.content;
    if (sess.content === localContent) {
      acknowledgedRef.current = { ...base, content: sess.content, revision: sess.revision };
    } else if (sess.content === base.content) {
      // The server still has the acknowledged version. Keep the local offline draft.
      acknowledgedRef.current = { ...base, revision: sess.revision };
    } else if (localContentDirty) {
      showRemoteConflict({ content: { content: sess.content, revision: sess.revision } });
    } else {
      acknowledgedRef.current = { ...base, content: sess.content, revision: sess.revision };
      contentRef.current = sess.content;
      setContent(sess.content);
    }

    const remoteMeta = { ...DEFAULT_META, ...(sess.meta || {}) };
    const remoteMetaJson = serializeMetadata(remoteMeta);
    const localMetaJson = serializeMetadata(metaRef.current);
    const localMetaDirty = localMetaJson !== base.meta;
    if (remoteMetaJson === localMetaJson) {
      acknowledgedRef.current = {
        ...(acknowledgedRef.current || base),
        meta: remoteMetaJson,
        metaRevision: sess.meta_revision,
      };
    } else if (remoteMetaJson === base.meta) {
      acknowledgedRef.current = {
        ...(acknowledgedRef.current || base),
        meta: remoteMetaJson,
        metaRevision: sess.meta_revision,
      };
    } else if (localMetaDirty) {
      showRemoteConflict({ meta: { meta: sess.meta, revision: sess.meta_revision } });
    } else {
      acknowledgedRef.current = {
        ...(acknowledgedRef.current || base),
        meta: remoteMetaJson,
        metaRevision: sess.meta_revision,
      };
      metaRef.current = remoteMeta;
      setMeta(remoteMeta);
    }
  };

  const reconcileSessionAfterReconnect = async (token: string): Promise<void> => {
    try {
      const snapshot = await initSession(token);
      if (token !== activeTokenRef.current) return;
      applyRemoteSessionSnapshot(snapshot);
      void restoreSessionImages(token, {
        images: snapshot.images || [],
        deleted: snapshot.deleted || [],
        image_revision: snapshot.image_revision,
      });
      if (!conflictRef.current) queueSessionSync(token);
      setSyncError(false);
    } catch (error) {
      console.warn('Failed to reconcile session after reconnect:', error);
      setSyncError(true);
    }
  };

  // Initialize the session on mount.
  useEffect(() => {
    void initializeBrowserSession();
  }, []);

  // Subscribe to agent events over SSE, reconnecting when the token changes.
  useEffect(() => {
    if (!sessionToken) return;

    let firstConnection = true;
    const unsubscribe = subscribeToSessionEvents(sessionToken, (evt) => {
      if (sessionToken !== activeTokenRef.current) return;
      if (evt.type === 'content_updated' && evt.revision) {
        const base = acknowledgedRef.current;
        let remoteContent: string | null = typeof evt.content === 'string' ? evt.content : null;
        if (remoteContent === null && evt.content_patches && evt.content_base_revision
          && base?.revision === evt.content_base_revision) {
          try {
            remoteContent = applyContentPatches(base.content, evt.content_patches);
          } catch {
            remoteContent = null;
          }
        }
        if (remoteContent !== null) {
          if (evt.client_id === clientIdRef.current) {
            if (base) acknowledgedRef.current = { ...base, content: remoteContent, revision: evt.revision };
          } else if (remoteContent === contentRef.current || remoteContent === inFlightRef.current?.content) {
            if (base) acknowledgedRef.current = { ...base, content: remoteContent, revision: evt.revision };
          } else if (conflictRef.current?.content || (base && contentRef.current !== base.content)) {
            showRemoteConflict({ content: { content: remoteContent, revision: evt.revision } });
          } else {
            if (base) acknowledgedRef.current = { ...base, content: remoteContent, revision: evt.revision };
            contentRef.current = remoteContent;
            setContent(remoteContent);
            if (evt.source === 'mcp_agent') showToast(evt.section ? `ИИ обновил раздел «${evt.section}»` : "ИИ обновил текст отчёта");
          }
        } else if (evt.content_patches) {
          void reconcileSessionAfterReconnect(sessionToken);
        }
      }
      if (evt.type === 'meta_updated' && evt.meta_revision) {
        const base = acknowledgedRef.current;
        let remoteMeta: ReportMetadata | null = evt.meta ? { ...DEFAULT_META, ...evt.meta } : null;
        if (!remoteMeta && evt.meta_patch && base
          && base.metaRevision === evt.meta_patch.base_revision
          && serializeMetadata(metaRef.current) === base.meta) {
          const next = { ...metaRef.current, ...evt.meta_patch.changed } as ReportMetadata;
          for (const key of evt.meta_patch.removed || []) delete (next as unknown as Record<string, unknown>)[key];
          remoteMeta = next;
        }
        if (!remoteMeta && evt.client_id === clientIdRef.current && inFlightRef.current?.meta) {
          try {
            remoteMeta = JSON.parse(inFlightRef.current.meta) as ReportMetadata;
          } catch {
            remoteMeta = null;
          }
        }
        if (remoteMeta) {
          const remoteMetaJson = serializeMetadata(remoteMeta);
          if (evt.client_id === clientIdRef.current) {
            if (base) acknowledgedRef.current = { ...base, meta: remoteMetaJson, metaRevision: evt.meta_revision };
          } else if (remoteMetaJson === serializeMetadata(metaRef.current) || remoteMetaJson === inFlightRef.current?.meta) {
            if (base) acknowledgedRef.current = { ...base, meta: remoteMetaJson, metaRevision: evt.meta_revision };
          } else if (conflictRef.current?.meta || (base && serializeMetadata(metaRef.current) !== base.meta)) {
            showRemoteConflict({ meta: { meta: remoteMeta, revision: evt.meta_revision } });
          } else {
            const message = metadataUpdateMessage(metaRef.current, remoteMeta);
            if (base) acknowledgedRef.current = { ...base, meta: remoteMetaJson, metaRevision: evt.meta_revision };
            metaRef.current = remoteMeta;
            setMeta(remoteMeta);
            if (evt.source === 'mcp_agent' && message) showToast(message);
          }
        } else if (evt.meta_patch) {
          void reconcileSessionAfterReconnect(sessionToken);
        }
      }
      if (evt.type === 'image_added' && evt.filename) {
        if (evt.client_id === clientIdRef.current) return;
        if (evt.image_revision) imageRevisionRef.current = evt.image_revision;
        const filename = evt.filename;
        void queueMediaOperation(async () => {
          if (sessionToken !== activeTokenRef.current) return;
          const newFile = await fetchSessionImageAsFile(sessionToken, filename);
          if (!newFile) throw new Error(`Не удалось получить изображение «${filename}»`);
          await saveStoredImage(newFile);
          if (sessionToken === activeTokenRef.current) {
            setImages(prev => {
              if (prev.some(f => f.name === newFile.name)) return prev;
              return [...prev, newFile];
            });
            if (evt.source === 'mcp_agent') {
              showToast(`ИИ прикрепил изображение «${filename}»`);
            }
          }
        }).catch(error => {
          console.warn('Failed to save agent image:', error);
          setLocalImageError(error instanceof Error ? error.message : 'Не удалось сохранить изображение');
        });
      }
      if (evt.type === 'image_deleted' && evt.filename) {
        if (evt.client_id === clientIdRef.current) return;
        if (evt.image_revision) imageRevisionRef.current = evt.image_revision;
        const filename = evt.filename;
        void queueMediaOperation(async () => {
          if (sessionToken !== activeTokenRef.current) return;
          const before = await getStoredImages();
          await deleteStoredImageByName(filename);
          const afterNames = new Set((await getStoredImages()).map(image => image.filename));
          const removedNames = new Set(before.filter(image => !afterNames.has(image.filename)).map(image => image.filename));
          setImages(prev => prev.filter(file => file.name !== filename && !removedNames.has(file.name)));
        }).catch(error => {
          console.warn('Failed to synchronize image deletion:', error);
          setLocalImageError(error instanceof Error ? error.message : 'Не удалось синхронизировать удаление');
        });
      }
    }, () => {
      if (firstConnection) {
        firstConnection = false;
        return;
      }
      void reconcileSessionAfterReconnect(sessionToken);
    });

    return () => {
      unsubscribe();
    };
  }, [sessionToken]);

  useEffect(() => {
    if (!sessionToken) return;
    const handleOnline = () => {
      syncRetryAttemptRef.current = 0;
      queueSessionSync(sessionToken);
    };
    window.addEventListener('online', handleOnline);
    return () => window.removeEventListener('online', handleOnline);
  }, [sessionToken]);

  // Synchronize browser edits to the session server with a one-second debounce.
  const syncTimeoutRef = useRef<any>(null);
  useEffect(() => {
    if (!sessionToken) return;
    if (syncTimeoutRef.current) clearTimeout(syncTimeoutRef.current);
    syncTimeoutRef.current = setTimeout(() => {
      queueSessionSync(sessionToken);
    }, 1000);
    return () => {
      if (syncTimeoutRef.current) clearTimeout(syncTimeoutRef.current);
    };
  }, [content, meta, sessionToken, syncConflict]);

  const handleResetSessionToken = async () => {
    try {
      clearStoredToken();
      if (syncRetryTimerRef.current) {
        clearTimeout(syncRetryTimerRef.current);
        syncRetryTimerRef.current = null;
      }
      syncRetryAttemptRef.current = 0;
      const sess = await initSession(null);
      sessionGenerationRef.current += 1;
      activeTokenRef.current = sess.token;
      imageRevisionRef.current = sess.image_revision;
      acknowledgedRef.current = { content: sess.content, revision: sess.revision,
        meta: serializeMetadata(sess.meta || {}), metaRevision: sess.meta_revision };
      conflictRef.current = null;
      setSyncConflict(null);
      setSessionToken(sess.token);
      void restoreSessionImages(sess.token, {
        images: sess.images || [],
        deleted: sess.deleted || [],
        image_revision: sess.image_revision,
      });
      showToast("Создан новый токен сессии");
    } catch {
      showToast("Ошибка при создании нового токена");
    }
  };

  const resolveContentConflict = (keepLocal: boolean) => {
    const remote = conflictRef.current?.content;
    const base = acknowledgedRef.current;
    if (!remote || !base) return;
    acknowledgedRef.current = { ...base, content: remote.content, revision: remote.revision };
    if (!keepLocal) {
      try { localStorage.setItem(`${REPORT_CONTENT_KEY}_before_conflict`, contentRef.current); } catch {}
      contentRef.current = remote.content;
      setContent(remote.content);
    }
    const next = { ...conflictRef.current };
    delete next.content;
    conflictRef.current = Object.keys(next).length ? next : null;
    setSyncConflict(conflictRef.current);
    if (keepLocal) queueSessionSync(sessionToken);
  };

  const resolveMetaConflict = (keepLocal: boolean) => {
    const remote = conflictRef.current?.meta;
    const base = acknowledgedRef.current;
    if (!remote || !base) return;
    acknowledgedRef.current = { ...base, meta: serializeMetadata({ ...DEFAULT_META, ...remote.meta }), metaRevision: remote.revision };
    if (!keepLocal) {
      try { localStorage.setItem(`${REPORT_META_KEY}_before_conflict`, JSON.stringify(metaRef.current)); } catch {}
      const nextMeta = { ...DEFAULT_META, ...remote.meta };
      metaRef.current = nextMeta;
      setMeta(nextMeta);
    }
    const next = { ...conflictRef.current };
    delete next.meta;
    conflictRef.current = Object.keys(next).length ? next : null;
    setSyncConflict(conflictRef.current);
    if (keepLocal) queueSessionSync(sessionToken);
  };

  const handleHeadingAlignmentChange = (align: 'left' | 'center') => {
    setMeta(prev => ({ ...prev, heading_alignment: align }));
  };

  const handlePageNumberingChange = (pos: 'center' | 'right' | 'none') => {
    setMeta(prev => ({ ...prev, page_numbering: pos }));
  };

  const handlePageBreakBeforeH1Change = (val: boolean) => {
    setMeta(prev => ({ ...prev, page_break_before_h1: val }));
  };

  const showToast = (msg: string) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToastMessage(msg);
    toastTimerRef.current = setTimeout(() => setToastMessage(null), 3500);
  };

  // File downloads.
  const triggerDownload = (blob: Blob, filename: string) => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => {
      try {
        URL.revokeObjectURL(url);
      } catch {}
    }, 1000);
  };

  // Cleared numeric fields can temporarily contain an empty string. Coerce
  // before sending to avoid HTTP 422 responses and filename errors.
  const sendMeta: ReportMetadata = {
    ...meta,
    work_number: Number(meta.work_number) || 1,
    year: Number(meta.year) || 2026,
    discipline: String(meta.discipline ?? ''),
  };

  const handleDownloadDocx = async () => {
    const missing = findMissingImageRefs(content, images);
    if (!confirmMissingImages(missing, findUnsupportedImageRefs(content))) {
      showToast("Скачивание отменено: прикрепите недостающие изображения");
      return;
    }
    setIsGenerating(true);
    persistLastNumber(Number(sendMeta.work_number) || 0);
    try {
      showToast("Сборка файла Word (.docx)...");
      const blob = await generateDocument(sendMeta, content, 'docx', images, {
        include_title_page: true,
        heading_alignment: sendMeta.heading_alignment || 'center',
        page_numbering: sendMeta.page_numbering || 'center',
        page_break_before_h1: sendMeta.page_break_before_h1 ?? false,
        hide_captions: sendMeta.hide_captions ?? false,
        latex_mode: sendMeta.latex_mode || 'omml'
      });
      const pfx = getWorkPrefix(sendMeta.work_type);
      const numStr = sendMeta.work_number ? `${sendMeta.work_number}` : '';
      const discStr = sendMeta.discipline ? `_${sendMeta.discipline.replace(/\s+/g, '_')}` : '';
      triggerDownload(blob, `Отчет_${pfx}${numStr}${discStr}.docx`);
      showToast("Документ Word скачан");
    } catch (err: any) {
      showToast(err.message || "Ошибка при генерации DOCX");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownloadPdf = async () => {
    if (!pdfExportEnabled) {
      showToast("PDF недоступен: экспортируйте DOCX в Office или установите совместимый конвертер");
      return;
    }
    const missing = findMissingImageRefs(content, images);
    if (!confirmMissingImages(missing, findUnsupportedImageRefs(content))) {
      showToast("Скачивание отменено: прикрепите недостающие изображения");
      return;
    }
    setIsGenerating(true);
    persistLastNumber(Number(sendMeta.work_number) || 0);
    try {
       showToast("Конвертация в PDF через локальный конвертер...");
      const blob = await generateDocument(sendMeta, content, 'pdf', images, {
        include_title_page: true,
        heading_alignment: sendMeta.heading_alignment || 'center',
        page_numbering: sendMeta.page_numbering || 'center',
        page_break_before_h1: sendMeta.page_break_before_h1 ?? false,
        hide_captions: sendMeta.hide_captions ?? false,
        latex_mode: sendMeta.latex_mode || 'omml'
      });
      const pfx = getWorkPrefix(sendMeta.work_type);
      const numStr = sendMeta.work_number ? `${sendMeta.work_number}` : '';
      const discStr = sendMeta.discipline ? `_${sendMeta.discipline.replace(/\s+/g, '_')}` : '';
      triggerDownload(blob, `Отчет_${pfx}${numStr}${discStr}.pdf`);
      showToast("PDF сгенерирован");
    } catch (err: any) {
      showToast(err.message || "Ошибка при экспорте в PDF");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownloadTitleOnly = async () => {
    setIsGenerating(true);
    persistLastNumber(Number(sendMeta.work_number) || 0);
    try {
      showToast("Генерация титульного листа...");
      const blob = await generateDocument(sendMeta, "", 'docx', [], { include_title_page: true });
      const pfx = getWorkPrefix(sendMeta.work_type);
      const numStr = sendMeta.work_number ? `${sendMeta.work_number}` : '';
      triggerDownload(blob, `Титульный_лист_${pfx}${numStr}.docx`);
      showToast("Титульный лист скачан");
    } catch (err: any) {
      showToast(err.message || "Ошибка при генерации титульного листа");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleAutofix = async () => {
    try {
      const res = await autofixMarkdown(content);
      setContent(res.fixed_content);
      showToast(`Применено исправлений: ${res.fixes_applied.length}`);
    } catch {
      showToast("Ошибка при автоисправлении");
    }
  };

  const handleExportJson = async () => {
    try {
      const exportedImages = await Promise.all(images.map(async file => ({
        filename: file.name,
        type: file.type || 'application/octet-stream',
        lastModified: file.lastModified,
        size_bytes: file.size,
        data: await fileToBase64(file),
      })));
      const project = { version: 2, meta, content, images: exportedImages };
      const blob = new Blob([JSON.stringify(project)], { type: 'application/json' });
      const pfx = getWorkPrefix(meta.work_type);
      const numStr = meta.work_number ? `${meta.work_number}` : '';
      const discStr = meta.discipline ? `_${meta.discipline.replace(/\s+/g, '_')}` : '';
      triggerDownload(blob, `Проект_${pfx}${numStr}${discStr}.json`);
      showToast("Проект сохранён в JSON вместе с изображениями");
    } catch {
      showToast("Не удалось сохранить проект в JSON");
    }
  };

  const profileSubject = (): SubjectPreset => {
    const stored = subjectPresets.find(subject => subject.id === activeSubjectId);
    return {
      id: stored?.id || `subj_${Date.now()}`,
      name: meta.discipline.trim() || stored?.name || 'Новая дисциплина',
      institute: meta.institute,
      department: meta.department,
      teachers: meta.teachers,
      custom_instructions: meta.custom_instructions || '',
      last_work_number: stored?.last_work_number || Number(meta.work_number) || undefined,
    };
  };

  const handleExportProfile = () => {
    try {
      const profile = createProfile(profileSubject(), sendMeta);
      const blob = new Blob([serializeProfile(profile)], { type: 'application/json' });
      triggerDownload(blob, profileFilename(profile.subject.name));
      showToast('Профиль дисциплины сохранён в JSON');
    } catch {
      showToast('Не удалось сохранить профиль в JSON');
    }
  };

  const handleImportProfile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    if (file.size > PROFILE_MAX_BYTES) {
      showToast('Файл профиля слишком велик (максимум 4 МБ)');
      return;
    }
    if (conflictRef.current?.meta || (acknowledgedRef.current && serializeMetadata(metaRef.current) !== acknowledgedRef.current.meta)) {
      showToast('Сначала синхронизируйте или разрешите конфликт реквизитов');
      return;
    }
    void file.text().then(raw => {
      let parsed: unknown;
      try {
        parsed = JSON.parse(raw);
      } catch {
        showToast('Профиль повреждён: некорректный JSON');
        return;
      }
      let profile;
      try {
        profile = parseProfile(parsed);
      } catch (error) {
        showToast(error instanceof Error ? error.message : 'Профиль повреждён');
        return;
      }
      const importedId = subjectPresets.some(subject => subject.id === profile.subject.id)
        ? `subj_${Date.now()}`
        : profile.subject.id;
      const importedSubject = { ...profile.subject, id: importedId };
      const importedProfile = { ...profile, subject: importedSubject };
      const nextMeta = applyProfile(importedProfile, metaRef.current);
      const updatedPresets = [...subjectPresets, importedSubject];
      setSubjectPresets(updatedPresets);
      saveSubjectPresets(updatedPresets);
      setActiveSubjectIdState(importedId);
      saveActiveSubjectId(importedId);
      metaRef.current = nextMeta;
      setMeta(nextMeta);
      if (sessionToken) queueSessionSync(sessionToken);
      showToast(`Профиль «${importedSubject.name}» импортирован`);
    }).catch(() => showToast('Не удалось прочитать файл профиля'));
  };

  const handleImportJson = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (file.size > 100 * 1024 * 1024) {
        showToast("Файл слишком велик (максимум 100 МБ)");
        e.target.value = '';
        return;
      }
      const reader = new FileReader();
      reader.onerror = () => {
        showToast("Ошибка при чтении файла");
      };
      reader.onload = evt => {
        try {
          const parsed = JSON.parse(evt.target?.result as string);
          if (isRecord(parsed) && typeof parsed.content === 'string' && isRecord(parsed.meta)) {
            const students = Array.isArray(parsed.meta.students)
              && parsed.meta.students.length > 0
              && parsed.meta.students.every(isStudentEntry)
                ? parsed.meta.students
                : DEFAULT_META.students;
            const teachers = Array.isArray(parsed.meta.teachers)
              && parsed.meta.teachers.length > 0
              && parsed.meta.teachers.every(isTeacherEntry)
                ? parsed.meta.teachers
                : DEFAULT_META.teachers;
              // Import cannot change the fixed doc_type; preserve university from the file.
              const restMeta = { ...parsed.meta };
              delete restMeta.doc_type;
              if (restMeta.logo_mode !== undefined) {
                restMeta.logo_mode = normalizeLogoMode(restMeta.logo_mode);
              }
              if (restMeta.references !== undefined
                && (!Array.isArray(restMeta.references) || !restMeta.references.every(isRecord))) {
                delete restMeta.references;
              }
              if (restMeta.image_layouts !== undefined && !isRecord(restMeta.image_layouts)) {
                delete restMeta.image_layouts;
              }
              if (restMeta.custom_logo !== undefined
                && restMeta.custom_logo !== null && typeof restMeta.custom_logo !== 'string') {
                delete restMeta.custom_logo;
              }
              setMeta({
                ...DEFAULT_META,
                ...restMeta,
                students,
                teachers
              });
              if (parsed.images !== undefined) {
                if (!Array.isArray(parsed.images) || parsed.images.length > 150) {
                  throw new Error('Некорректный список изображений');
                }
                const importedImages: File[] = [];
                const importedNames = new Set<string>();
                for (const entry of parsed.images) {
                  if (!isRecord(entry) || typeof entry.filename !== 'string'
                    || typeof entry.data !== 'string' || typeof entry.type !== 'string') {
                    throw new Error('Некорректное изображение в проекте');
                  }
                  if (importedNames.has(entry.filename)) throw new Error('Повторяющееся имя изображения');
                  importedNames.add(entry.filename);
                  const lastModified = typeof entry.lastModified === 'number' ? entry.lastModified : Date.now();
                  importedImages.push(base64ToFile(entry.data, entry.filename, entry.type, lastModified));
                }
                handleImagesChange(importedImages);
              }
            setContent(parsed.content);
            showToast("Проект загружен");
          } else {
            throw new Error('Некорректная структура проекта');
          }
        } catch {
          showToast("Неверный формат JSON файла");
        }
      };
      reader.readAsText(file);
    }
    e.target.value = '';
  };

  const handleApplyAiImport = (cleanedMarkdown: string, extractedTheme?: string, mode: 'replace' | 'append' = 'replace') => {
    if (mode === 'append') {
      setContent(prev => (prev ? prev + '\n\n' + cleanedMarkdown : cleanedMarkdown));
    } else {
      setContent(cleanedMarkdown);
    }
    if (extractedTheme) {
      setMeta(prev => ({ ...prev, work_theme: extractedTheme }));
    }
    showToast("Ответ ИИ импортирован");
  };

  return (
    <div className="h-screen h-[100dvh] flex flex-col overflow-hidden bg-slate-100 font-sans">
      <Header
        meta={meta}
        appVersion={versionInfo?.version}
        onDownloadDocx={handleDownloadDocx}
        onDownloadPdf={handleDownloadPdf}
        pdfExportEnabled={pdfExportEnabled}
        onDownloadTitleOnly={handleDownloadTitleOnly}
        onOpenVerifyModal={() => setIsVerifyModalOpen(true)}
        onOpenAiModal={() => setIsAiModalOpen(true)}
        onOpenMcpModal={() => setIsMcpModalOpen(true)}
        onOpenGuide={() => setIsGuideModalOpen(true)}
        onExportJson={handleExportJson}
        onImportJson={handleImportJson}
        onExportProfile={handleExportProfile}
        onImportProfile={handleImportProfile}
        isGenerating={isGenerating}
      />

      {versionInfo?.update.status === 'available' && !updateDismissed && (
        <div role="status" className="flex items-center justify-between gap-3 border-b border-blue-200 bg-blue-50 px-3 py-2 text-xs text-blue-950 sm:px-5">
          <span>
            Доступна новая версия {versionInfo.update.latest_version}.
            {versionInfo.update.release_url && (
              <> <a className="font-semibold underline underline-offset-2" href={versionInfo.update.release_url} target="_blank" rel="noreferrer">Открыть релиз</a>.</>
            )}
          </span>
          <button
            type="button"
            aria-label="Скрыть уведомление об обновлении"
            onClick={() => setUpdateDismissed(true)}
            className="shrink-0 rounded px-1.5 py-0.5 text-blue-700 hover:bg-blue-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-700"
          >
            ×
          </button>
        </div>
      )}

      {/* Mobile editor/A4 preview switch. */}
      <div className="lg:hidden px-2.5 pt-2 pb-1 bg-slate-100 shrink-0 border-b border-slate-200">
        <div className="grid grid-cols-2 gap-1 bg-slate-200/90 p-1 rounded-xl text-xs font-bold shadow-inner">
          <button
            type="button"
            onClick={() => setMobileTab('editor')}
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-lg transition-all ${
              mobileTab === 'editor'
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <FileEdit className="h-3.5 w-3.5" />
            <span>Редактор и форма</span>
          </button>
          <button
            type="button"
            onClick={() => setMobileTab('preview')}
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-lg transition-all ${
              mobileTab === 'preview'
                ? 'bg-white text-blue-700 shadow-sm'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Eye className="h-3.5 w-3.5" />
            <span>Предпросмотр А4</span>
          </button>
        </div>
      </div>

      {/* Toast notification. */}
      {toastMessage && (
        <div className="fixed bottom-5 right-5 z-50 rounded-xl bg-slate-900 text-white px-4 py-2.5 text-xs font-semibold shadow-2xl flex items-center gap-2 animate-in fade-in duration-150">
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Below lg, mobileTab selects one full-height column.
          At lg and above, both columns appear side by side. */}
      <main className="flex-1 p-2 sm:p-4 grid grid-cols-1 lg:grid-cols-12 gap-3 lg:gap-4 max-w-[1800px] w-full mx-auto overflow-hidden min-h-0">
        {/* Left column. */}
        <section className={`${mobileTab === 'editor' ? 'flex' : 'hidden'} lg:flex lg:col-span-6 flex-col gap-2 sm:gap-2.5 h-full overflow-hidden min-h-0`}>
          {/* Compact subject picker and text/title-page switch. */}
          <div className="flex flex-wrap items-center justify-between gap-2 bg-white rounded-xl border border-slate-200 p-2 shrink-0 shadow-sm">
            {/* Subject and work number. */}
            <div className="flex items-center gap-2 flex-1 min-w-0">
              <div className="flex items-center gap-1.5 flex-1 min-w-0 max-w-xs">
                <BookOpen className="h-3.5 w-3.5 text-blue-600 shrink-0" />
                <select
                  value={activeSubjectId}
                  onChange={e => handleSwitchSubject(e.target.value)}
                  className="w-full truncate rounded-lg border border-slate-300 bg-slate-50 px-2 py-1 text-xs font-bold text-slate-800 focus:outline-none focus:border-blue-500"
                  title="Выбрать семестровую дисциплину"
                >
                  {subjectPresets.length === 0 ? (
                    <option value="">(Без шаблона)</option>
                  ) : (
                    <>
                      <option value="">(Без шаблона)</option>
                      {subjectPresets.map(sp => (
                        <option key={sp.id} value={sp.id}>{sp.name}</option>
                      ))}
                    </>
                  )}
                </select>
                <button
                  type="button"
                  onClick={() => {
                    setSubjectModalMode('create');
                    setSubjectModalName(meta.discipline || '');
                    setIsSubjectModalOpen(true);
                  }}
                  className="p-1 text-blue-600 hover:bg-blue-50 rounded-md shrink-0 transition-colors"
                  title="Добавить новый шаблон дисциплины"
                >
                  <Plus className="h-3.5 w-3.5" />
                </button>
              </div>

              <div className="flex items-center gap-1 shrink-0">
                <span className="text-[11px] font-bold text-slate-500">{workTypeShort}</span>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={meta.work_number}
                  onChange={e => setMeta(prev => ({ ...prev, work_number: parseInt(e.target.value) || 1 }))}
                  className="w-12 rounded-lg border border-slate-300 px-1.5 py-1 text-xs font-bold text-center text-slate-900 focus:outline-none focus:border-blue-500"
                  title="Номер работы"
                />
              </div>
            </div>

            {/* Text/title-page switch. */}
            <div className="flex items-center gap-1 bg-slate-100 p-0.5 rounded-lg shrink-0">
              <button
                type="button"
                onClick={() => setLeftView('editor')}
                className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-md text-xs font-bold transition-all ${
                  leftView === 'editor'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <FileEdit className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Текст работы</span>
                <span className="sm:hidden">Текст</span>
              </button>

              <button
                type="button"
                onClick={() => setLeftView('settings')}
                className={`flex items-center gap-1.5 px-2.5 sm:px-3 py-1 rounded-md text-xs font-bold transition-all ${
                  leftView === 'settings'
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'text-slate-600 hover:text-slate-900'
                }`}
              >
                <Settings2 className="h-3.5 w-3.5" />
                <span className="hidden sm:inline">Титульник и профиль</span>
                <span className="sm:hidden">Титульник</span>
              </button>
            </div>
          </div>

          {syncConflict?.content && (
            <div role="alert" className="border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              <p className="font-semibold">Текст изменён в другой вкладке или агентом</p>
              <p className="mt-1">Ваш черновик остаётся в редакторе. Сравните версии и выберите, какую сохранить.</p>
              <details className="mt-1">
                <summary className="cursor-pointer underline underline-offset-2">Посмотреть другую версию</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-white p-2 text-slate-700">{syncConflict.content.content}</pre>
              </details>
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" onClick={() => resolveContentConflict(true)} className="rounded-md bg-amber-900 px-2.5 py-1.5 text-white hover:bg-amber-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Сохранить мой текст</button>
                <button type="button" onClick={() => resolveContentConflict(false)} className="rounded-md border border-amber-300 bg-white px-2.5 py-1.5 hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Принять другую версию</button>
              </div>
            </div>
          )}
          {syncConflict?.meta && (
            <div role="alert" className="border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              <p className="font-semibold">Реквизиты отчёта изменились в другой вкладке</p>
              <p className="mt-1">Ваши значения сохранены. Проверьте другую версию перед выбором.</p>
              <details className="mt-1">
                <summary className="cursor-pointer underline underline-offset-2">Посмотреть реквизиты</summary>
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded bg-white p-2 text-slate-700">{JSON.stringify(syncConflict.meta.meta, null, 2)}</pre>
              </details>
              <div className="mt-2 flex flex-wrap gap-2">
                <button type="button" onClick={() => resolveMetaConflict(true)} className="rounded-md bg-amber-900 px-2.5 py-1.5 text-white hover:bg-amber-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Сохранить мои реквизиты</button>
                <button type="button" onClick={() => resolveMetaConflict(false)} className="rounded-md border border-amber-300 bg-white px-2.5 py-1.5 hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Принять другую версию</button>
              </div>
            </div>
          )}
          {syncError && !syncConflict && (
            <div role="status" className="flex items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              <span>Сервер недоступен. Черновик сохранён в браузере.</span>
              <button type="button" onClick={() => queueSessionSync(sessionToken)} className="shrink-0 rounded-md border border-amber-300 px-2.5 py-1.5 hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Повторить</button>
            </div>
          )}
          {failedImageUploads.length > 0 && (
            <div role="alert" className="flex items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              <span>Не удалось передать изображения в сессию. Проверьте локальное сохранение и повторите отправку.</span>
              <button type="button" disabled={retryingImageUploads} onClick={() => {
                setRetryingImageUploads(true);
                void uploadImagesToSession(failedImageUploads.filter(file => images.includes(file)))
                  .finally(() => setRetryingImageUploads(false));
              }} className="shrink-0 rounded-md border border-amber-300 px-2.5 py-1.5 hover:bg-amber-100 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Повторить</button>
            </div>
          )}
          {localImageError && (
            <div role="alert" className="flex items-center justify-between gap-2 border-b border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-950">
              <span>Изображения требуют проверки: {localImageError}</span>
              <button type="button" onClick={() => void (sessionToken ? restoreSessionImages(sessionToken) : initializeBrowserSession())} className="shrink-0 rounded-md border border-amber-300 px-2.5 py-1.5 hover:bg-amber-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-900">Проверить снова</button>
            </div>
          )}

          {/* Full-height editor workspace. */}
          <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
            {leftView === 'editor' ? (
              <MarkdownEditor
                content={content}
                onChange={nextContent => { contentRef.current = nextContent; setContent(nextContent); }}
                images={images}
                onImagesChange={handleImagesChange}
                imageLayouts={meta.image_layouts}
                onImageLayoutChange={(name, layout) => setMeta(prev => ({
                  ...prev, image_layouts: { ...prev.image_layouts, [name]: layout }
                }))}
                onOpenTableModal={() => setIsTableModalOpen(true)}
                onRegisterInsert={registerEditorInsert}
                selectionRef={editorSelectionRef}
              />
            ) : (
              <MetadataForm
                meta={meta}
                onChange={setMeta}
                activeSubjectId={activeSubjectId}
                onSubjectChange={handleSwitchSubject}
                subjectPresets={subjectPresets}
                onPresetsChange={setSubjectPresets}
                onDeletePreset={(id) => {
                  const found = subjectPresets.find(p => p.id === id);
                  setSubjectModalMode('delete');
                  setSubjectModalName(found?.name || '');
                  setSubjectModalTargetId(id);
                  setIsSubjectModalOpen(true);
                }}
              />
            )}
          </div>
        </section>

        {/* Right column: A4 preview and compliance checks. */}
        <section className={`${mobileTab === 'preview' ? 'flex' : 'hidden'} lg:flex lg:col-span-6 flex-col h-full overflow-hidden min-h-0`}>
          <DocumentPreview
            meta={meta}
            content={content}
            images={images}
            onAutofix={handleAutofix}
            headingAlignment={meta.heading_alignment || 'center'}
            onHeadingAlignmentChange={handleHeadingAlignmentChange}
            pageNumbering={meta.page_numbering || 'center'}
            onPageNumberingChange={handlePageNumberingChange}
            pageBreakBeforeH1={meta.page_break_before_h1 ?? false}
            onPageBreakBeforeH1Change={handlePageBreakBeforeH1Change}
            onHideCaptionsChange={(val) => setMeta(prev => ({ ...prev, hide_captions: val }))}
            latexMode={meta.latex_mode || 'omml'}
            onLatexModeChange={(mode) => setMeta(prev => ({ ...prev, latex_mode: mode }))}
          />
        </section>
      </main>

      {/* Visual table builder modal. */}
      {isTableModalOpen && (
        <TableModal
          isOpen={isTableModalOpen}
          onClose={() => setIsTableModalOpen(false)}
          onInsert={tableMd => {
            const text = '\n' + tableMd;
            setMobileTab('editor');
            const insert = insertIntoEditorRef.current;
            if (insert) {
              insert(text);
            } else {
              pendingEditorInsertRef.current = text;
              setLeftView('editor');
            }
          }}
        />
      )}

      {/* External DOCX audit modal. */}
      {isVerifyModalOpen && (
        <ExternalVerifyModal
          isOpen={isVerifyModalOpen}
          onClose={() => setIsVerifyModalOpen(false)}
        />
      )}

      {/* AI prompt generation and import modal. */}
      {isAiModalOpen && (
        <AiPromptModal
          isOpen={isAiModalOpen}
          onClose={() => setIsAiModalOpen(false)}
          onApplyImport={handleApplyAiImport}
          meta={meta}
          onUpdateCustomInstructions={(val) => setMeta(prev => ({ ...prev, custom_instructions: val }))}
          onUpdatePromptLatex={(val) => setMeta(prev => ({ ...prev, prompt_latex: val }))}
          onUpdatePromptCodeBlocks={(val) => setMeta(prev => ({ ...prev, prompt_code_blocks: val }))}
        />
      )}

      {/* MCP agent connection modal. */}
      {isMcpModalOpen && (
        <McpModal
          isOpen={isMcpModalOpen}
          onClose={() => setIsMcpModalOpen(false)}
          token={sessionToken}
          onResetToken={handleResetSessionToken}
        />
      )}

      {isGuideModalOpen && (
        <ReportGuideModal
          onClose={() => setIsGuideModalOpen(false)}
          onVerify={() => {
            setIsGuideModalOpen(false);
            setIsVerifyModalOpen(true);
          }}
        />
      )}

      {/* Subject preset creation/deletion modal. */}
      {isSubjectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4">
          <div className="w-full max-w-sm rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 bg-slate-50/80">
              <h2 className="text-sm font-bold text-slate-900">
                {subjectModalMode === 'create' ? 'Новый шаблон дисциплины' : 'Удалить шаблон?'}
              </h2>
              <p className="text-[11px] text-slate-500 mt-0.5">
                {subjectModalMode === 'create'
                  ? 'Настройки кафедры и преподавателя сохранятся для всех работ по этой дисциплине.'
                  : `Шаблон «${subjectModalName}» будет удален из списка.`}
              </p>
            </div>
            <div className="px-5 py-4">
              {subjectModalMode === 'create' ? (
                <input
                  autoFocus
                  type="text"
                  value={subjectModalName}
                  onChange={e => setSubjectModalName(e.target.value)}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      handleCreateNewSubject(subjectModalName);
                      setIsSubjectModalOpen(false);
                    }
                    if (e.key === 'Escape') setIsSubjectModalOpen(false);
                  }}
                  placeholder="Название дисциплины (например: Физика)"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-900 focus:outline-none focus:border-blue-500 font-medium"
                />
              ) : (
                <p className="text-xs text-slate-700">
                  Подтвердите удаление шаблона <strong>«{subjectModalName}»</strong>. Действие нельзя отменить.
                </p>
              )}
            </div>
            <div className="px-5 py-3 bg-slate-50 border-t border-slate-200 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setIsSubjectModalOpen(false)}
                className="rounded-lg border border-slate-300 bg-white px-4 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition-colors"
              >
                Отмена
              </button>
              <button
                type="button"
                onClick={() => {
                  if (subjectModalMode === 'create') {
                    handleCreateNewSubject(subjectModalName);
                  } else {
                    handleDeleteSubject(subjectModalTargetId);
                  }
                  setIsSubjectModalOpen(false);
                }}
                disabled={subjectModalMode === 'create' && !subjectModalName.trim()}
                className={`rounded-lg px-4 py-1.5 text-xs font-bold text-white transition-all disabled:opacity-50 ${
                  subjectModalMode === 'create'
                    ? 'bg-blue-600 hover:bg-blue-700'
                    : 'bg-red-600 hover:bg-red-700'
                }`}
              >
                {subjectModalMode === 'create' ? 'Создать' : 'Удалить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
