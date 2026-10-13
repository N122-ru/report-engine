/**
 * Synchronize live report sessions with the MCP agent.
 */

import { fetchWithTimeout, retryAfterMs } from './http.ts';

const STORAGE_KEY = 'report_session_token';
const CLIENT_ID_KEY = 'report_session_client_id';
let fallbackClientId: string | null = null;

// JSON key order is not a metadata edit. Arrays retain their meaningful order.
export const serializeMetadata = (meta: unknown): string => JSON.stringify(meta, (_key, value) => {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return Object.fromEntries(Object.keys(value).sort().map(key => [key, value[key]]));
  }
  return value;
}) ?? '';

export const metadataUpdateMessage = (
  before: object, after: object,
): string | null => {
  const previous = new Map(Object.entries(before));
  const next = new Map(Object.entries(after));
  const changed = [...new Set([...previous.keys(), ...next.keys()])]
    .filter(key => serializeMetadata(previous.get(key)) !== serializeMetadata(next.get(key)));
  if (changed.length === 0) return null;
  if (changed.every(key => key === 'image_layouts')) return 'ИИ обновил размещение рисунков';
  if (changed.every(key => key === 'references')) return 'ИИ обновил список источников';
  return 'ИИ обновил реквизиты отчёта';
};

export interface SessionImageItem {
  filename: string;
  size_bytes: number;
  size_kb: number;
  sha256?: string;
  width_px?: number | null;
  height_px?: number | null;
  mime_type: string;
  is_in_report: boolean;
  url: string;
}

export interface SessionInitResponse {
  token: string;
  content: string;
  revision: string;
  meta_revision: string;
  image_revision?: string;
  meta: any;
  images?: SessionImageItem[];
  deleted?: string[];
}

export interface SessionImagesResponse {
  images: SessionImageItem[];
  deleted: string[];
  image_revision?: string;
}

export interface SessionSyncPayload {
  content?: string;
  content_patches?: ContentPatch[];
  meta?: any;
  expected_revision?: string;
  expected_meta_revision?: string;
  client_id?: string;
}

export interface ContentPatch {
  start: number;
  delete_count: number;
  insert: string;
}

export type SessionSyncResult =
  | { status: 'ok'; revision: string; meta_revision: string }
  | { status: 'conflict'; conflict_type: 'content'; revision: string; content: string }
  | { status: 'conflict'; conflict_type: 'meta'; meta_revision: string; meta: any };

export interface LiveSyncEvent {
  type: 'content_updated' | 'meta_updated' | 'image_added' | 'image_deleted';
  source?: string;
  section?: string;
  content?: string;
  content_patches?: ContentPatch[];
  content_base_revision?: string;
  revision?: string;
  meta_revision?: string;
  image_revision?: string;
  meta?: any;
  meta_patch?: {
    base_revision: string;
    changed: Record<string, unknown>;
    removed?: string[];
  };
  filename?: string;
  size?: number;
  url?: string;
  caption?: string;
  timestamp: number;
  client_id?: string;
}

export const buildContentPatches = (before: string, after: string): ContentPatch[] => {
  const beforeChars = Array.from(before);
  const afterChars = Array.from(after);
  let start = 0;
  while (start < beforeChars.length && start < afterChars.length && beforeChars[start] === afterChars[start]) start += 1;
  let beforeEnd = beforeChars.length;
  let afterEnd = afterChars.length;
  while (beforeEnd > start && afterEnd > start && beforeChars[beforeEnd - 1] === afterChars[afterEnd - 1]) {
    beforeEnd -= 1;
    afterEnd -= 1;
  }
  return [{
    start,
    delete_count: beforeEnd - start,
    insert: afterChars.slice(start, afterEnd).join(''),
  }];
};

export const applyContentPatches = (content: string, patches: ContentPatch[]): string => {
  const chars = Array.from(content);
  const ordered = [...patches].sort((left, right) => right.start - left.start);
  for (const patch of ordered) {
    if (!Number.isInteger(patch.start) || !Number.isInteger(patch.delete_count)
      || patch.start < 0 || patch.delete_count < 0
      || patch.start + patch.delete_count > chars.length) {
      throw new Error('Некорректная дельта текста');
    }
    chars.splice(patch.start, patch.delete_count, ...Array.from(patch.insert));
  }
  return chars.join('');
};

export const getClientId = (): string => {
  try {
    const existing = sessionStorage.getItem(CLIENT_ID_KEY);
    if (existing) return existing;
    const created = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    sessionStorage.setItem(CLIENT_ID_KEY, created);
    return created;
  } catch {
    if (!fallbackClientId) {
      fallbackClientId = `client-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    return fallbackClientId;
  }
};

export const getStoredToken = (): string | null => {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
};

export const storeToken = (token: string): void => {
  try {
    localStorage.setItem(STORAGE_KEY, token);
  } catch {
    // ignore
  }
};

export const clearStoredToken = (): void => {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // ignore
  }
};

/**
 * Initialize a backend session or restore a saved session.
 */
export const initSession = async (token?: string | null): Promise<SessionInitResponse> => {
  const currentToken = token === undefined ? getStoredToken() : token;
  const url = currentToken 
    ? `/api/session/init?token=${encodeURIComponent(currentToken)}` 
    : '/api/session/init';

  const res = await fetchWithTimeout(url);
  if (!res.ok) {
    throw new Error('Не удалось инициализировать сессию');
  }
  const data: SessionInitResponse = await res.json();
  if (data.token) {
    storeToken(data.token);
  }
  return data;
};

/**
 * Synchronize current browser changes to the server.
 */
export const syncSessionToServer = async (
  token: string,
  payload: SessionSyncPayload
): Promise<SessionSyncResult> => {
  if (!token) throw new Error('Сессия не инициализирована');
  const response = await fetchWithTimeout(`/api/session/${encodeURIComponent(token)}/sync`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ...payload, client_id: payload.client_id || getClientId() })
  });
  if (!response.ok && response.status !== 409) {
    const error = new Error(`Не удалось синхронизировать отчёт (${response.status})`) as Error & { retryAfterMs?: number };
    error.retryAfterMs = retryAfterMs(response);
    throw error;
  }
  return response.json() as Promise<SessionSyncResult>;
};

/**
 * Subscribe to live MCP agent updates over SSE.
 */
export const subscribeToSessionEvents = (
  token: string,
  onEvent: (event: LiveSyncEvent) => void,
  onConnected?: () => void,
): (() => void) => {
  if (!token) return () => {};

  const es = new EventSource(`/api/session/${encodeURIComponent(token)}/events`);
  es.addEventListener('connected', () => onConnected?.());

  es.addEventListener('sync', (msg: MessageEvent) => {
    try {
      const data: LiveSyncEvent = JSON.parse(msg.data);
      onEvent(data);
    } catch (e) {
      console.error('Failed to parse SSE event:', e);
    }
  });

  es.onerror = () => {
      // EventSource automatically attempts to reconnect.
  };

  return () => {
    es.close();
  };
};

/**
 * Upload image files to the current server session.
 */
export const uploadSessionImages = async (
  token: string,
  files: File[],
  restoring = false,
): Promise<{ filename: string; size_bytes: number; url: string; image_revision?: string }[]> => {
  if (!token || files.length === 0) return [];
  const formData = new FormData();
  files.forEach(f => formData.append('files', f));

  const params = new URLSearchParams({ client_id: getClientId() });
  if (restoring) params.set('restoring', 'true');
  const res = await fetchWithTimeout(`/api/session/${encodeURIComponent(token)}/images?${params.toString()}`, {
    method: 'POST',
    body: formData,
  }, 60_000);
  if (!res.ok) {
    throw new Error(`Upload failed: ${res.statusText}`);
  }
  const data = await res.json();
  if (!Array.isArray(data.uploaded) || data.uploaded.length !== files.length) {
    throw new Error('Неполный ответ сервера при загрузке изображений');
  }
  return data.uploaded;
};

export const getSessionImages = async (token: string): Promise<SessionImagesResponse> => {
  const response = await fetchWithTimeout(`/api/session/${encodeURIComponent(token)}/images`);
  if (!response.ok) throw new Error('Не удалось получить список изображений сессии');
  const data = await response.json();
  if (!Array.isArray(data.images)) throw new Error('Некорректный список изображений сессии');
  return {
    images: data.images,
    deleted: Array.isArray(data.deleted) ? data.deleted : [],
    image_revision: typeof data.image_revision === 'string' ? data.image_revision : undefined,
  };
};

/**
 * Delete an image from the server session.
 */
export const deleteSessionImage = async (
  token: string,
  filename: string,
  expectedImageRevision?: string,
): Promise<{ image_revision?: string }> => {
  if (!token || !filename) return {};
  const params = new URLSearchParams({ client_id: getClientId() });
  if (expectedImageRevision) params.set('expected_image_revision', expectedImageRevision);
  const response = await fetchWithTimeout(`/api/session/${encodeURIComponent(token)}/images/${encodeURIComponent(filename)}?${params.toString()}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error(`Не удалось удалить изображение (${response.status})`);
  const data = await response.json();
  return { image_revision: typeof data.image_revision === 'string' ? data.image_revision : undefined };
};

/**
 * Download a session image and return a File object.
 */
export const fetchSessionImageAsFile = async (
  token: string,
  filename: string,
  mimeType: string = 'image/png'
): Promise<File | null> => {
  if (!token || !filename) return null;
  try {
    const res = await fetchWithTimeout(`/api/session/${encodeURIComponent(token)}/images/${encodeURIComponent(filename)}`, {}, 60_000);
    if (!res.ok) return null;
    const blob = await res.blob();
    return new File([blob], filename, { type: blob.type || mimeType });
  } catch (err) {
    console.warn('Failed to fetch session image:', err);
    return null;
  }
};
