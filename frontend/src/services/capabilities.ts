import { fetchWithTimeout } from './http.ts';

export interface RuntimeCapabilities {
  pdf_export: boolean;
  pdf_converter: 'office' | 'docbuilder' | null;
}

const API_BASE = (import.meta as ImportMeta & {
  env?: { VITE_API_URL?: string };
}).env?.VITE_API_URL || '';

export async function getRuntimeCapabilities(): Promise<RuntimeCapabilities> {
  const response = await fetchWithTimeout(`${API_BASE}/api/capabilities`, {}, 5_000);
  if (!response.ok) {
    throw new Error('Не удалось получить возможности локального сервера');
  }
  return response.json() as Promise<RuntimeCapabilities>;
}
