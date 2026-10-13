export type MediaSort = 'name-asc' | 'name-desc' | 'size-desc';

const filenameOrder = new Intl.Collator('ru', { numeric: true, sensitivity: 'base' });
const imageTypes: Record<string, string> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', gif: 'image/gif',
  webp: 'image/webp', bmp: 'image/bmp', svg: 'image/svg+xml',
  tif: 'image/tiff', tiff: 'image/tiff', avif: 'image/avif', ico: 'image/x-icon',
};

const uploadName = (name: string): string =>
  (name.replaceAll('\\', '/').split('/').pop() || '').trim().replace(/[^\p{L}\p{N}_.-]/gu, '_');

export function mergeImageFiles(existing: File[], incoming: Iterable<File>) {
  const names = new Set(existing.map(file => uploadName(file.name)));
  const added: File[] = [];
  const rejected: string[] = [];
  const duplicates: string[] = [];
  for (const file of incoming) {
    const extension = file.name.split('.').pop()?.toLowerCase() || '';
    const type = file.type.startsWith('image/') ? file.type
      : (!file.type || file.type === 'application/octet-stream') ? imageTypes[extension] : undefined;
    if (!type) {
      rejected.push(file.name);
      continue;
    }
    const name = uploadName(file.name);
    if (names.has(name)) {
      duplicates.push(file.name);
      continue;
    }
    names.add(name);
    added.push(file.type === type ? file : new File([file], file.name, { type, lastModified: file.lastModified }));
  }
  return { images: [...existing, ...added], added, rejected, duplicates };
}

export function sortMediaFiles(images: File[], mode: MediaSort): File[] {
  return [...images].sort((left, right) => {
    const byName = filenameOrder.compare(left.name, right.name);
    if (mode === 'size-desc') return right.size - left.size || byName;
    return mode === 'name-desc' ? -byName : byName;
  });
}
