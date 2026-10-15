/** Shared filename normalization for browser-side report image references. */

export const decodeImageRef = (value: string): string => {
  const trimmed = value.trim().replace(/^<|>$/g, '');
  try {
    return decodeURIComponent(trimmed);
  } catch {
    return trimmed;
  }
};

export const imageRefBasename = (value: string): string =>
  decodeImageRef(value).replaceAll('\\', '/').split('/').pop() || '';

export const canonicalImageName = (value: string): string =>
  imageRefBasename(value).toLowerCase().replace(/[^\p{L}\p{N}]/gu, '');

export const isExternalImageRef = (value: string): boolean =>
  /^(?:https?:|data:|blob:)/i.test(decodeImageRef(value));

/** Resolve a reference only when a normalized filename match is unambiguous. */
export const resolveImageName = (reference: string, names: string[]): string | undefined => {
  const decoded = decodeImageRef(reference);
  const basename = imageRefBasename(decoded);
  const candidates = [reference, decoded, basename];

  for (const candidate of candidates) {
    const exact = names.filter(name => name === candidate);
    if (exact.length === 1) return exact[0];
    const caseInsensitive = names.filter(name => name.toLowerCase() === candidate.toLowerCase());
    if (caseInsensitive.length === 1) return caseInsensitive[0];
  }

  const canonical = canonicalImageName(reference);
  if (!canonical) return undefined;
  const matches = names.filter(name => canonicalImageName(name) === canonical);
  return matches.length === 1 ? matches[0] : undefined;
};

export const imageNamesMatch = (left: string, right: string): boolean => {
  const leftCanonical = canonicalImageName(left);
  return Boolean(leftCanonical) && leftCanonical === canonicalImageName(right);
};
