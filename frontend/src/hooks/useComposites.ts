/**
 * Hook for managing user-defined composite metrics in localStorage.
 * Composites are math formulas combining two indicators (e.g., SMA20 / SMA200 * 100).
 */
import { useState, useCallback, useEffect } from 'react';

const STORAGE_KEY = 'tradecraft.screener.composites.v1';

export type CompositeOperation = 'add' | 'subtract' | 'multiply' | 'divide' | 'ratio_pct';

export interface UserComposite {
  id: string;
  name: string;
  description?: string;
  leftIndicator: string;
  rightIndicator: string;
  operation: CompositeOperation;
  createdAt: number;
  updatedAt?: number;
}

export interface UseCompositesReturn {
  composites: UserComposite[];
  saveComposite: (data: Omit<UserComposite, 'id' | 'createdAt'>) => UserComposite;
  deleteComposite: (id: string) => void;
  getCompositeById: (id: string) => UserComposite | undefined;
}

function generateId(): string {
  return 'comp_' + Date.now().toString(36) + '_' + Math.random().toString(36).substring(2, 9);
}

function loadFromStorage(): UserComposite[] {
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

function saveToStorage(composites: UserComposite[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(composites));
  } catch {
    // ignore quota errors
  }
}

export function useComposites(): UseCompositesReturn {
  const [composites, setComposites] = useState<UserComposite[]>(loadFromStorage);

  useEffect(() => {
    saveToStorage(composites);
  }, [composites]);

  const saveComposite = useCallback((data: Omit<UserComposite, 'id' | 'createdAt'>): UserComposite => {
    const now = Date.now();
    const newComposite: UserComposite = {
      id: generateId(),
      createdAt: now,
      ...data,
    };
    setComposites(prev => {
      // Update if same name exists, otherwise append
      const existing = prev.findIndex(c => c.name === data.name);
      if (existing >= 0) {
        const updated = [...prev];
        updated[existing] = { ...updated[existing], ...newComposite, updatedAt: now };
        return updated;
      }
      return [...prev, newComposite];
    });
    return newComposite;
  }, []);

  const deleteComposite = useCallback((id: string) => {
    setComposites(prev => prev.filter(c => c.id !== id));
  }, []);

  const getCompositeById = useCallback((id: string): UserComposite | undefined => {
    return composites.find(c => c.id === id);
  }, [composites]);

  return { composites, saveComposite, deleteComposite, getCompositeById };
}
