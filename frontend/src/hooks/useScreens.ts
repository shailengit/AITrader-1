/**
 * Hook for managing Custom Screener presets in localStorage.
 * Provides CRUD operations, draft management, and template loading.
 */
import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY_PRESETS = 'tradecraft.screener.presets.v1';
const STORAGE_KEY_DRAFT = 'tradecraft.screener.draft';

export interface FilterGroup {
  match: 'all' | 'any';
  conditions: FilterCondition[];
}

export interface FilterCondition {
  id: string;
  filterKey: string;
  operator: string;
  value: unknown;
  referenceFilterKey?: string;
  lookbackDays?: number;
  params?: Record<string, number>;
  referenceParams?: Record<string, number>;
  compareToIndicator?: boolean;
}

export interface ScreenPreset {
  schemaVersion: 1;
  id: string;
  name: string;
  description?: string;
  isTemplate: boolean;
  parentId?: string;
  createdAt: number;
  updatedAt: number;
  lastUsedAt?: number;
  filters: FilterGroup;
  sort?: { by: string; order: 'asc' | 'desc' };
  maxResults: number;
  cutoffDate?: string;
  useAi: boolean;
  category?: string;
  tags?: string[];
  // Scoring tunables (added 2026-07-05). All optional — defaults applied on load.
  baseWeight?: number; // 0–100, default 60
  subWeights?: {
    trend: number;     // 0–100, default 30
    momentum: number;  // 0–100, default 25
    volatility: number; // 0–100, default 20
    volume: number;    // 0–100, default 25
  };
  showAlignment?: boolean; // default false
}

export interface UseScreensReturn {
  presets: ScreenPreset[];
  draft: Partial<ScreenPreset> | null;
  loading: boolean;
  savePreset: (preset: Omit<ScreenPreset, 'schemaVersion' | 'id' | 'createdAt' | 'updatedAt' | 'isTemplate'>) => ScreenPreset;
  updatePreset: (id: string, updates: Partial<ScreenPreset>) => void;
  deletePreset: (id: string) => void;
  loadPreset: (id: string) => ScreenPreset | undefined;
  saveDraft: (draft: Partial<ScreenPreset>) => void;
  clearDraft: () => void;
  forkPreset: (id: string, newName: string) => ScreenPreset | null;
  getPresetById: (id: string) => ScreenPreset | undefined;
}

function generateId(): string {
  return 'scr_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 9);
}

function loadPresetsFromStorage(): ScreenPreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_PRESETS);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch {
    return [];
  }
}

function savePresetsToStorage(presets: ScreenPreset[]): void {
  try {
    localStorage.setItem(STORAGE_KEY_PRESETS, JSON.stringify(presets));
  } catch (e) {
    if (e instanceof DOMException && e.name === 'QuotaExceededError') {
      throw new Error('Storage full. Delete old screens to save more.');
    }
    throw e;
  }
}

function loadDraftFromStorage(): Partial<ScreenPreset> | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_DRAFT);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export function useScreens(): UseScreensReturn {
  const [presets, setPresets] = useState<ScreenPreset[]>(loadPresetsFromStorage);
  const [draft, setDraft] = useState<Partial<ScreenPreset> | null>(loadDraftFromStorage);
  const [loading] = useState(false);

  // Sync presets to localStorage on change
  useEffect(() => {
    savePresetsToStorage(presets);
  }, [presets]);

  const savePreset = useCallback((data: Omit<ScreenPreset, 'schemaVersion' | 'id' | 'createdAt' | 'updatedAt' | 'isTemplate'>): ScreenPreset => {
    const now = Date.now();
    const newPreset: ScreenPreset = {
      schemaVersion: 1,
      id: generateId(),
      isTemplate: false,
      createdAt: now,
      updatedAt: now,
      ...data,
    };
    setPresets(prev => {
      const existing = prev.findIndex(p => p.id === newPreset.id);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = newPreset;
        return updated;
      }
      return [...prev, newPreset];
    });
    // Clear draft on save
    try { localStorage.removeItem(STORAGE_KEY_DRAFT); } catch { /* ignore */ }
    setDraft(null);
    return newPreset;
  }, []);

  const updatePreset = useCallback((id: string, updates: Partial<ScreenPreset>) => {
    setPresets(prev => prev.map(p =>
      p.id === id ? { ...p, ...updates, updatedAt: Date.now() } : p
    ));
  }, []);

  const deletePreset = useCallback((id: string) => {
    setPresets(prev => prev.filter(p => p.id !== id));
  }, []);

  const loadPreset = useCallback((id: string): ScreenPreset | undefined => {
    const preset = presets.find(p => p.id === id);
    if (preset) {
      updatePreset(id, { lastUsedAt: Date.now() });
    }
    return preset;
  }, [presets, updatePreset]);

  const saveDraft = useCallback((draftData: Partial<ScreenPreset>) => {
    setDraft(draftData);
    try {
      localStorage.setItem(STORAGE_KEY_DRAFT, JSON.stringify(draftData));
    } catch { /* ignore quota errors for drafts */ }
  }, []);

  const clearDraft = useCallback(() => {
    setDraft(null);
    try { localStorage.removeItem(STORAGE_KEY_DRAFT); } catch { /* ignore */ }
  }, []);

  const forkPreset = useCallback((id: string, newName: string): ScreenPreset | null => {
    const source = presets.find(p => p.id === id);
    if (!source) return null;
    const now = Date.now();
    const fork: ScreenPreset = {
      ...source,
      id: generateId(),
      name: newName,
      isTemplate: false,
      parentId: source.isTemplate ? undefined : source.id,
      createdAt: now,
      updatedAt: now,
      lastUsedAt: now,
    };
    setPresets(prev => [...prev, fork]);
    return fork;
  }, [presets]);

  const getPresetById = useCallback((id: string): ScreenPreset | undefined => {
    return presets.find(p => p.id === id);
  }, [presets]);

  return {
    presets,
    draft,
    loading,
    savePreset,
    updatePreset,
    deletePreset,
    loadPreset,
    saveDraft,
    clearDraft,
    forkPreset,
    getPresetById,
  };
}
