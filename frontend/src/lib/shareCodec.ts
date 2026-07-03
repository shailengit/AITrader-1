/**
 * Share codec for Custom Screener.
 * Encodes/decodes ScreenPreset to/from lz-string + base64url for share URLs.
 */
import LZString from 'lz-string';

export interface ShareData {
  schemaVersion: 1;
  name: string;
  description?: string;
  filters: { match: 'all' | 'any'; conditions: unknown[] };
  sort?: { by: string; order: 'asc' | 'desc' };
  maxResults: number;
  cutoffDate?: string;
  useAi: boolean;
}

/**
 * Encode a screen preset into a base64url string for sharing.
 * Uses lz-string compression to keep URLs manageable (~500 chars for 30 filters).
 */
export function encodeShareUrl(data: ShareData): string {
  const json = JSON.stringify(data);
  const compressed = LZString.compressToEncodedURIComponent(json);
  return compressed;
}

/**
 * Decode a base64url string back into a screen preset.
 * Returns null if the string is malformed or can't be decoded.
 */
export function decodeShareUrl(encoded: string): ShareData | null {
  try {
    const json = LZString.decompressFromEncodedURIComponent(encoded);
    if (!json) return null;
    const data = JSON.parse(json) as ShareData;
    if (!data.schemaVersion || !data.filters) return null;
    return data;
  } catch {
    return null;
  }
}

/**
 * Build a full share URL from encoded data.
 */
export function buildShareUrl(encoded: string): string {
  return `${window.location.origin}/app/screener/build?s=${encoded}`;
}
