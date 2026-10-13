export class RequestTimeoutError extends Error {
  constructor(message = 'Время ожидания запроса истекло') {
    super(message);
    this.name = 'RequestTimeoutError';
  }
}

export const fetchWithTimeout = async (
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = 15_000,
): Promise<Response> => {
  const controller = new AbortController();
  const timeoutId = globalThis.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted) {
      throw new RequestTimeoutError(`Запрос не завершился за ${Math.ceil(timeoutMs / 1000)} с`);
    }
    throw error;
  } finally {
    globalThis.clearTimeout(timeoutId);
  }
};

export const retryAfterMs = (response: Response): number | undefined => {
  const value = response.headers.get('Retry-After');
  if (!value) return undefined;
  const seconds = Number(value);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? Math.max(0, timestamp - Date.now()) : undefined;
};
