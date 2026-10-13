import { fetchWithTimeout } from './http.ts';

export type UpdateStatus = 'disabled' | 'current' | 'available' | 'unavailable';

export interface VersionInfo {
  version: string;
  update: {
    status: UpdateStatus;
    latest_version: string | null;
    release_url: string | null;
  };
}

const API_BASE = (import.meta as ImportMeta & {
  env?: { VITE_API_URL?: string };
}).env?.VITE_API_URL || '';

export async function getVersionInfo(): Promise<VersionInfo> {
  const response = await fetchWithTimeout(`${API_BASE}/api/version`, {}, 5_000);
  if (!response.ok) {
    throw new Error('Не удалось получить версию приложения');
  }
  return response.json() as Promise<VersionInfo>;
}
