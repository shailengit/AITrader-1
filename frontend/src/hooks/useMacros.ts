/**
 * Hook for managing user-defined macro filter groups in localStorage.
 * Macros are saved groups of conditions that can be expanded into the builder.
 */
import { useState, useCallback, useEffect } from 'react';
import type { FilterGroup } from './useScreens';

const STORAGE_KEY = 'tradecraft.screener.macros.v1';

export interface MacroPreset {
  id: string;
  name: string;
  description?: string;
  filters: FilterGroup;
  createdAt: number;
  updatedAt: number;
}

export interface UseMacrosReturn {
  macros: MacroPreset[];
  saveMacro: (name: string, filters: FilterGroup, description?: string) => MacroPreset;
  deleteMacro: (id: string) => void;
  getMacroById: (id: string) => MacroPreset | undefined;
}

function generateId(): string {
  return 'macro_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 9);
}

function loadFromStorage(): MacroPreset[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed;
  } catch {
    return [];
  }
}

function saveToStorage(macros: MacroPreset[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(macros));
  } catch {
    // ignore quota errors
  }
}

export function useMacros(): UseMacrosReturn {
  const [macros, setMacros] = useState<MacroPreset[]>(loadFromStorage);

  useEffect(() => {
    saveToStorage(macros);
  }, [macros]);

  const saveMacro = useCallback((name: string, filters: FilterGroup, description?: string): MacroPreset => {
    const now = Date.now();
    const existing = macros.find(m => m.name === name);
    if (existing) {
      const updated = { ...existing, filters, description, updatedAt: now };
      setMacros(prev => prev.map(m => m.id === existing.id ? updated : m));
      return updated;
    }
    const newMacro: MacroPreset = {
      id: generateId(),
      name,
      description,
      filters,
      createdAt: now,
      updatedAt: now,
    };
    setMacros(prev => [...prev, newMacro]);
    return newMacro;
  }, [macros]);

  const deleteMacro = useCallback((id: string) => {
    setMacros(prev => prev.filter(m => m.id !== id));
  }, []);

  const getMacroById = useCallback((id: string): MacroPreset | undefined => {
    return macros.find(m => m.id === id);
  }, [macros]);

  return { macros, saveMacro, deleteMacro, getMacroById };
}
