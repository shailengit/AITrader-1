import { useEffect, useState, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import { strategyLabApi, type StrategySession, type ExperimentRow, type BatchStats, type SummarizeResponse, type RefineStrategyResponse } from "../../lib/strategyLab";
import { Button } from "../../components/ui/Button";
import { DiffReview } from "../../components/strategy-lab/DiffReview";

interface StepBacktestProps {
  session: StrategySession;
  onWinnerPicked: (experimentId: string) => void;
}

export function StepBacktest({ session, onWinnerPicked }: StepBacktestProps) {
  const [nRuns, setNRuns] = useState(10);
  const [endDate, setEndDate] = useState("2024-01-01");
  const [startDateMin, setStartDateMin] = useState("2022-01-01");
  const [startDateMax, setStartDateMax] = useState("2024-01-01");
  const [batchId, setBatchId] = useState<string | null>(null);
  const [experiments, setExperiments] = useState<ExperimentRow[]>([]);
  const [stats, setStats] = useState<BatchStats | null>(null);
  const [progress, setProgress] = useState({ completed: 0, total: 0 });
  const [summary, setSummary] = useState<SummarizeResponse | null>(null);
  const [refine, setRefine] = useState<RefineStrategyResponse | null>(null);
  const [selectedWinner, setSelectedWinner] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Start a batch
  const start = useMutation({
    mutationFn: () =>
      strategyLabApi.startExperiments(session.id, {
        n_runs: nRuns,
        end_date: endDate,
        start_date_min: startDateMin,
        start_date_max: startDateMax,
      }),
    onSuccess: (r) => {
      setBatchId(r.batch_id);
      setExperiments([]);
      setStats(null);
      setSummary(null);
      setRefine(null);
      setProgress({ completed: 0, total: nRuns });
    },
  });

  // Poll for results
  useEffect(() => {
    if (!batchId) return;
    const poll = async () => {
      try {
        const [rows, s] = await Promise.all([
          strategyLabApi.listBatchExperiments(session.id, batchId),
          strategyLabApi.getBatchStats(session.id, batchId),
        ]);
        setExperiments(rows);
        setStats(s);
        setProgress({ completed: s.n_completed, total: s.n_total });
        if (s.n_completed + s.n_failed >= nRuns) {
          // Done
          if (pollRef.current) clearInterval(pollRef.current);
        }
      } catch (e) {
        // ignore
      }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [batchId, nRuns, session.id]);

  // AI summarize
  const summarize = useMutation({
    mutationFn: () => strategyLabApi.summarizeBatch(session.id, batchId!, { model: session.model_id }),
    onSuccess: (r) => setSummary(r),
  });

  // AI refine
  const refineMut = useMutation({
    mutationFn: () => strategyLabApi.refineAfterBatch(session.id, batchId!, { model: session.model_id }),
    onSuccess: (r) => setRefine(r),
  });

  // Apply refine diff
  const apply = useMutation({
    mutationFn: (diff: string) =>
      strategyLabApi.applyDiff(session.id, { instruction: diff }),
    onSuccess: () => {
      setRefine(null);
      // Re-run the batch with the new code
      setTimeout(() => start.mutate(), 500);
    },
  });

  const isRunning = !!batchId && progress.completed + (stats?.n_failed || 0) < nRuns;
  const isDone = !!batchId && !isRunning;

  return (
    <div className="space-y-6 p-6">
      <header>
        <h2 className="text-xl font-semibold text-zinc-100">4. Run experiments</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Run {nRuns} backtests with random as-of-date windows to test robustness.
        </p>
      </header>

      {!batchId && (
        <div className="space-y-4 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <div>
              <label className="mb-1 block text-sm text-zinc-300">Runs</label>
              <input
                type="number"
                min={1}
                max={500}
                value={nRuns}
                onChange={(e) => setNRuns(Math.max(1, Math.min(500, parseInt(e.target.value) || 1)))}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-300">End date</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-300">Start min</label>
              <input
                type="date"
                value={startDateMin}
                onChange={(e) => setStartDateMin(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm text-zinc-300">Start max</label>
              <input
                type="date"
                value={startDateMax}
                onChange={(e) => setStartDateMax(e.target.value)}
                className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>
          <Button onClick={() => start.mutate()} disabled={start.isPending}>
            {start.isPending ? "Starting…" : `▶ Start ${nRuns}-run batch`}
          </Button>
        </div>
      )}

      {batchId && (
        <div className="space-y-4">
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-3">
            <div className="flex items-center justify-between text-sm">
              <span className="text-zinc-300">
                Progress: {progress.completed}/{progress.total} completed
                {stats && stats.n_failed > 0 ? `, ${stats.n_failed} failed` : ""}
              </span>
              <span className="font-mono text-xs text-zinc-500">
                batch {batchId.slice(0, 8)}…
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded bg-zinc-800">
              <div
                className="h-full bg-emerald-500 transition-all duration-300"
                style={{ width: `${progress.total > 0 ? (progress.completed / progress.total) * 100 : 0}%` }}
              />
            </div>
          </div>

          {experiments.length > 0 && (
            <div className="overflow-x-auto rounded-lg border border-zinc-800">
              <table className="w-full text-sm">
                <thead className="bg-zinc-900/50 text-zinc-400">
                  <tr>
                    <th className="px-3 py-2 text-left">#</th>
                    <th className="px-3 py-2 text-left">Start</th>
                    <th className="px-3 py-2 text-right">Return</th>
                    <th className="px-3 py-2 text-right">α</th>
                    <th className="px-3 py-2 text-right">WR</th>
                    <th className="px-3 py-2 text-right">PF</th>
                    <th className="px-3 py-2 text-right">Trades</th>
                    <th className="px-3 py-2 text-right">Sharpe*</th>
                    <th className="px-3 py-2 text-center">Status</th>
                    <th className="px-3 py-2 text-center">Pick</th>
                  </tr>
                </thead>
                <tbody>
                  {experiments
                    .slice()
                    .sort((a, b) => a.run_index - b.run_index)
                    .map((row) => {
                      const k = row.kpis;
                      const ret = k?.total_return_pct;
                      const sharpe = ret != null && k?.max_drawdown_pct ? ret / Math.abs(k.max_drawdown_pct) : null;
                      return (
                        <tr
                          key={row.id}
                          className={`border-t border-zinc-800 ${
                            selectedWinner === row.id ? "bg-emerald-950/30" : ""
                          }`}
                        >
                          <td className="px-3 py-2 text-zinc-400">{row.run_index}</td>
                          <td className="px-3 py-2 text-zinc-300">{row.start_date?.slice(0, 10) ?? "—"}</td>
                          <td className={`px-3 py-2 text-right font-mono ${ret != null && ret >= 0 ? "text-emerald-400" : "text-red-400"}`}>
                            {ret != null ? `${ret.toFixed(1)}%` : "—"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-zinc-300">
                            {k?.alpha_pct != null ? `${k.alpha_pct.toFixed(1)}%` : "—"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-zinc-300">
                            {k?.win_rate != null ? `${k.win_rate.toFixed(1)}%` : "—"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-zinc-300">
                            {k?.profit_factor != null ? k.profit_factor.toFixed(2) : "—"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-zinc-300">
                            {k?.total_trades ?? "—"}
                          </td>
                          <td className="px-3 py-2 text-right font-mono text-zinc-300">
                            {sharpe != null ? sharpe.toFixed(2) : "—"}
                          </td>
                          <td className="px-3 py-2 text-center text-xs">
                            {row.status === "completed" ? (
                              <span className="rounded bg-emerald-900/50 px-2 py-0.5 text-emerald-300">ok</span>
                            ) : (
                              <span className="rounded bg-red-900/50 px-2 py-0.5 text-red-300" title={row.error_message ?? ""}>
                                failed
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-center">
                            {row.status === "completed" && (
                              <button
                                onClick={() => {
                                  setSelectedWinner(row.id);
                                  onWinnerPicked(row.id);
                                }}
                                className="text-xs text-blue-400 hover:text-blue-300"
                              >
                                {selectedWinner === row.id ? "✓ picked" : "pick"}
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>
          )}

          {isDone && stats && stats.n_completed > 0 && (
            <div className="flex flex-wrap gap-2">
              <Button onClick={() => summarize.mutate()} disabled={summarize.isPending} variant="secondary">
                {summarize.isPending ? "Analyzing…" : "🤖 AI Summary"}
              </Button>
              <Button onClick={() => refineMut.mutate()} disabled={refineMut.isPending} variant="secondary">
                {refineMut.isPending ? "Refining…" : "🔄 Refine Strategy"}
              </Button>
              <Button onClick={() => { setBatchId(null); }} variant="ghost">
                Run another batch
              </Button>
            </div>
          )}

          {summary && (
            <div className="rounded-lg border border-blue-800 bg-blue-950/20 p-4">
              <h3 className="mb-2 text-sm font-semibold text-blue-200">AI Summary</h3>
              <p className="whitespace-pre-wrap text-sm text-zinc-200">{summary.summary_text}</p>
            </div>
          )}

          {refine && (
            <div className="rounded-lg border border-amber-800 bg-amber-950/20 p-4">
              <h3 className="mb-2 text-sm font-semibold text-amber-200">
                Suggested code change
              </h3>
              <p className="mb-3 text-xs text-zinc-400">{refine.rationale}</p>
              <DiffReview
                diff={refine.diff}
                summary={refine.summary}
                onAccept={() => apply.mutate(refine.diff)}
                onReject={() => setRefine(null)}
                isApplying={apply.isPending}
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}
