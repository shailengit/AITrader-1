import { useQuery, useMutation } from "@tanstack/react-query";

export interface ScreenerMode {
  id: string;
  name: string;
  description: string;
  agents: string[];
  supports_backtesting: boolean;
}

export interface ScanRequest {
  mode: "dormant_giant" | "quant_strategy";
  use_ai: boolean;
  cutoff_date?: string;
  prompt?: string;
  max_results: number;
  filters?: Record<string, unknown>;
  base_weight?: number;
}

export interface ScanStatus {
  scan_id: string;
  mode: string;
  status: "pending" | "running" | "completed" | "failed";
  progress: number;
  use_ai: boolean;
  results_count: number;
  has_ai_report: boolean;
  error?: string;
}

async function fetchModes(): Promise<ScreenerMode[]> {
  const res = await fetch("/api/screener/modes");
  if (!res.ok) throw new Error("Failed to load screener modes");
  const data = await res.json();
  return data.modes;
}

async function fetchScanStatus(scanId: string): Promise<ScanStatus> {
  const res = await fetch(`/api/screener/status/${scanId}`);
  if (!res.ok) throw new Error("Failed to fetch scan status");
  return res.json();
}

async function fetchScanResults(scanId: string): Promise<Record<string, unknown>[]> {
  const res = await fetch(`/api/screener/results/${scanId}`);
  if (!res.ok) throw new Error("Failed to fetch scan results");
  return res.json();
}

async function fetchAIReport(scanId: string): Promise<string> {
  const res = await fetch(`/api/screener/ai-report/${scanId}`);
  if (!res.ok) throw new Error("Failed to fetch AI report");
  const data = await res.json();
  return data.report || "";
}

async function parseFilters(prompt: string): Promise<Record<string, unknown>> {
  const res = await fetch("/api/screener/parse-filters", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt }),
  });
  if (!res.ok) throw new Error("Failed to parse filters");
  const data = await res.json();
  return data.filters;
}

async function startScan(request: ScanRequest): Promise<{ scan_id: string }> {
  const res = await fetch("/api/screener/scan", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(request),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to start scan");
  }
  return res.json();
}

export function useScreenerModes() {
  return useQuery({
    queryKey: ["screener", "modes"],
    queryFn: fetchModes,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });
}

export function useScanStatus(scanId: string | null, options?: { refetchInterval?: number }) {
  return useQuery({
    queryKey: ["screener", "scan", scanId, "status"],
    queryFn: () => fetchScanStatus(scanId!),
    enabled: !!scanId,
    refetchInterval: options?.refetchInterval ?? 2000,
  });
}

export function useScanResults(scanId: string | null) {
  return useQuery({
    queryKey: ["screener", "scan", scanId, "results"],
    queryFn: () => fetchScanResults(scanId!),
    enabled: !!scanId,
  });
}

export function useAIReport(scanId: string | null) {
  return useQuery({
    queryKey: ["screener", "scan", scanId, "ai-report"],
    queryFn: () => fetchAIReport(scanId!),
    enabled: !!scanId,
  });
}

export function useParseFilters() {
  return useMutation({
    mutationFn: parseFilters,
  });
}

export function useStartScan() {
  return useMutation({
    mutationFn: startScan,
  });
}
