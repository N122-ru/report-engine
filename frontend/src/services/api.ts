import { ReportMetadata, GenerateOptions, LinterResult } from '../types';
import { fetchWithTimeout } from './http.ts';

export { getVersionInfo } from './update.ts';
export type { VersionInfo } from './update.ts';
export { getRuntimeCapabilities } from './capabilities.ts';
export type { RuntimeCapabilities } from './capabilities.ts';

const API_BASE = import.meta.env.VITE_API_URL || '';

function formatApiError(errData: any, fallbackMsg: string): string {
  if (!errData) return fallbackMsg;
  if (typeof errData.detail === 'string') return errData.detail;
  if (Array.isArray(errData.detail)) {
    return errData.detail
      .map((item: any) => {
        const field = item.loc ? item.loc[item.loc.length - 1] : '';
        return field ? `${field}: ${item.msg}` : (item.msg || JSON.stringify(item));
      })
      .join('; ');
  }
  return fallbackMsg;
}

export async function generateDocument(
  meta: ReportMetadata,
  content: string,
  format: 'docx' | 'pdf',
  images: File[],
  options?: Partial<GenerateOptions>
): Promise<Blob> {
  const formData = new FormData();
  formData.append('meta', JSON.stringify(meta));
  formData.append('content', content);
  formData.append('format', format);

  if (options) {
    formData.append('options', JSON.stringify(options));
  }

  images.forEach(img => {
    formData.append('images', img);
  });

  const res = await fetchWithTimeout(`${API_BASE}/api/generate`, {
    method: 'POST',
    body: formData,
  }, 120_000);

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(errData, "Ошибка при сборке документа"));
  }

  return res.blob();
}

export async function verifyExternalFile(file: File): Promise<LinterResult> {
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetchWithTimeout(`${API_BASE}/api/verify`, {
    method: 'POST',
    body: formData,
  }, 60_000);

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(errData, "Ошибка при проверке файла"));
  }

  return res.json();
}

export async function autofixMarkdown(content: string): Promise<{ fixed_content: string; fixes_applied: string[] }> {
  const formData = new FormData();
  formData.append('content', content);

  const res = await fetchWithTimeout(`${API_BASE}/api/autofix`, {
    method: 'POST',
    body: formData,
  }, 30_000);

  if (!res.ok) {
    const errData = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(formatApiError(errData, "Не удалось выполнить автоисправление"));
  }

  return res.json();
}
