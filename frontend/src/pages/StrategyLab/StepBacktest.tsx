import { useEffect, useState, useRef, useMemo } from "react";
import { useMutation } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Play, Sparkles, RotateCcw, AlertCircle, FileText } from "lucide-react";
import {
  strategyLabApi,
  type StrategySession,
  type ExperimentRow,
  type BatchStats,
  type SummarizeResponse,
  type RefineStrategyResponse,
} from "../../lib/strategyLab";
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
  const [progress, setProgress] = useState({ completed: 0, total: 0, failed: 0 });
  const [summary, setSummary] = useState<SummarizeResponse | null>(null);
  const [refine, setRefine] = useState<RefineStrategyResponse | null>(null);
  const [selectedWinner, setSelectedWinner] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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
      setSelectedWinner(null);
      setProgress({ completed: 0, total: nRuns, failed: 0 });
    },
  });

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
        setProgress({ completed: s.n_completed, total: s.n_total, failed: s.n_failed });
        if (s.n_completed + s.n_failed >= nRuns && pollRef.current) {
          clearInterval(pollRef.current);
        }
      } catch {
        // ignore transient poll errors
      }
    };
    poll();
    pollRef.current = setInterval(poll, 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [batchId, nRuns, session.id]);

  const summarize = useMutation({
    mutationFn: () => strategyLabApi.summarizeBatch(session.id, batchId!, { model: session.model_id }),
    onSuccess: (r) => setSummary(r),
  });

  const refineMut = useMutation({
    mutationFn: () => strategyLabApi.refineAfterBatch(session.id, batchId!, { model: session.model_id }),
    onSuccess: (r) => setRefine(r),
  });

  const apply = useMutation({
    mutationFn: (diff: string) => strategyLabApi.applyDiff(session.id, { instruction: diff }),
    onSuccess: () => {
      setRefine(null);
      setTimeout(() => start.mutate(), 500);
    },
  });

  const isRunning = !!batchId && progress.completed + progress.failed < nRuns;
  const isDone = !!batchId && !isRunning;

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// 04 · Backtest</div>
          <h1 className="slab-page-head__title">Validate it.</h1>
          <p className="slab-page-head__lede">
            Run randomized as-of-date windows to see how the strategy holds
            up across regimes. Pick the best run, then deploy.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Phase · Validate</span>
          <span
            className={
              isRunning
                ? "slab-status slab-status--live"
                : isDone
                  ? "slab-status slab-status--terminal"
                  : "slab-status slab-status--dim"
            }
          >
            <span className="slab-status__dot" />
            {isRunning ? "RUNNING" : isDone ? "COMPLETE" : "IDLE"}
          </span>
        </div>
      </div>

      <div className="slab-page-body">
        {!batchId && (
          <ConfigForm
            nRuns={nRuns}
            setNRuns={setNRuns}
            endDate={endDate}
            setEndDate={setEndDate}
            startDateMin={startDateMin}
            setStartDateMin={setStartDateMin}
            startDateMax={startDateMax}
            setStartDateMax={setStartDateMax}
            onStart={() => start.mutate()}
            isStarting={start.isPending}
            error={start.error as Error | null}
          />
        )}

        {batchId && (
          <>
            <LiveTicker
              completed={progress.completed}
              total={progress.total}
              failed={progress.failed}
              isRunning={isRunning}
              batchId={batchId}
            />

            {experiments.length > 0 && (
              <ExperimentTable
                rows={experiments}
                selectedWinner={selectedWinner}
                onPick={(id) => {
                  setSelectedWinner(id);
                  onWinnerPicked(id);
                }}
              />
            )}

            {isDone && stats && stats.n_completed > 0 && (
              <PostBatchActions
                onSummarize={() => summarize.mutate()}
                isSummarizing={summarize.isPending}
                onRefine={() => refineMut.mutate()}
                isRefining={refineMut.isPending}
                onAnotherBatch={() => setBatchId(null)}
                summary={summary}
                refine={refine}
                onAcceptRefine={(d) => apply.mutate(d)}
                onRejectRefine={() => setRefine(null)}
                isApplying={apply.isPending}
              />
            )}
          </>
        )}
      </div>
    </>
  );
}

// ── Configuration form ─────────────────────────────────────────────────
function ConfigForm(props: {
  nRuns: number; setNRuns: (n: number) => void;
  endDate: string; setEndDate: (s: string) => void;
  startDateMin: string; setStartDateMin: (s: string) => void;
  startDateMax: string; setStartDateMax: (s: string) => void;
  onStart: () => void; isStarting: boolean; error: Error | null;
}) {
  return (
    <div style={{ maxWidth: 920 }}>
      <div
        className="slab-eyebrow"
        style={{ marginBottom: 16, color: "var(--slab-paper-faint)" }}
      >
        // Batch parameters
      </div>
      <div className="slab-grid-4">
        <div className="slab-field">
          <label className="slab-field__label">Runs</label>
          <input
            type="number"
            min={1}
            max={500}
            value={props.nRuns}
            onChange={(e) => props.setNRuns(Math.max(1, Math.min(500, parseInt(e.target.value) || 1)))}
            className="slab-input"
            style={{ fontSize: 16 }}
          />
        </div>
        <div className="slab-field">
          <label className="slab-field__label">End date</label>
          <input
            type="date"
            value={props.endDate}
            onChange={(e) => props.setEndDate(e.target.value)}
            className="slab-input"
          />
        </div>
        <div className="slab-field">
          <label className="slab-field__label">Start min</label>
          <input
            type="date"
            value={props.startDateMin}
            onChange={(e) => props.setStartDateMin(e.target.value)}
            className="slab-input"
          />
        </div>
        <div className="slab-field">
          <label className="slab-field__label">Start max</label>
          <input
            type="date"
            value={props.startDateMax}
            onChange={(e) => props.setStartDateMax(e.target.value)}
            className="slab-input"
          />
        </div>
      </div>

      <div style={{ marginTop: 28, display: "flex", alignItems: "center", gap: 16 }}>
        <button
          type="button"
          onClick={props.onStart}
          disabled={props.isStarting}
          className="slab-btn slab-btn--terminal"
          style={{ padding: "12px 24px" }}
        >
          <Play size={12} fill="currentColor" />
          {props.isStarting ? "Starting…" : `Start ${props.nRuns}-run batch`}
        </button>
        {props.error && (
          <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <AlertCircle size={12} />
            {String(props.error?.message ?? "Failed to start")}
          </span>
        )}
      </div>
    </div>
  );
}

// ── Live ticker — three big numbers + a progress bar ──────────────────
function LiveTicker({ completed, total, failed, isRunning, batchId }: {
  completed: number; total: number; failed: number; isRunning: boolean; batchId: string;
}) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div className="slab-panel" style={{ maxWidth: 1280 }}>
      <div className="slab-panel__head">
        <span className="slab-eyebrow slab-eyebrow--gold">// Live</span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">batch · {batchId.slice(0, 8)}</span>
      </div>
      <div style={{ padding: 24, display: "grid", gridTemplateColumns: "repeat(3, 1fr) auto", gap: 32, alignItems: "center" }}>
        <div>
          <div className="slab-ticker__label">Completed</div>
          <div className="slab-ticker">
            <span className="slab-ticker--gold">{String(completed).padStart(3, "0")}</span>
            <span className="slab-mono slab-mono--lg slab-mono--faint">/{total}</span>
          </div>
        </div>
        <div>
          <div className="slab-ticker__label">Failed</div>
          <div className="slab-ticker">
            <span style={{ color: failed > 0 ? "var(--slab-rose)" : "var(--slab-paper-faint)" }}>
              {String(failed).padStart(3, "0")}
            </span>
          </div>
        </div>
        <div>
          <div className="slab-ticker__label">Progress</div>
          <div className="slab-ticker">
            {String(pct).padStart(2, "0")}<span className="slab-mono slab-mono--lg slab-mono--faint">%</span>
          </div>
        </div>
        <div>
          <span className={isRunning ? "slab-status slab-status--live" : "slab-status slab-status--terminal"}>
            <span className="slab-status__dot" />
            {isRunning ? "Running" : "Complete"}
          </span>
        </div>
      </div>
      {/* hairline progress bar */}
      <div style={{ height: 2, background: "var(--slab-rule)" }}>
        <motion.div
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.4 }}
          style={{
            height: "100%",
            background: isRunning ? "var(--slab-gold)" : "var(--slab-terminal)",
            boxShadow: isRunning ? "0 0 12px var(--slab-gold-glow)" : "none",
          }}
        />
      </div>
    </div>
  );
}

// ── Experiments table ─────────────────────────────────────────────────
function ExperimentTable({ rows, selectedWinner, onPick }: {
  rows: ExperimentRow[]; selectedWinner: string | null;
  onPick: (id: string) => void;
}) {
  const sorted = useMemoSortByIndex(rows);

  return (
    <div className="slab-panel" style={{ maxWidth: 1280, marginTop: 24 }}>
      <div className="slab-panel__head">
        <span className="slab-eyebrow slab-eyebrow--gold">// Runs</span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">
          click <span style={{ color: "var(--slab-gold)" }}>pick</span> to mark the winner
        </span>
      </div>
      <div style={{ maxHeight: 480, overflow: "auto" }}>
        <table className="slab-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Start</th>
              <th className="slab-table__num">Return</th>
              <th className="slab-table__num">α</th>
              <th className="slab-table__num">WR</th>
              <th className="slab-table__num">PF</th>
              <th className="slab-table__num">Trades</th>
              <th className="slab-table__num">Sharpe*</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((row) => (
              <ExperimentRowView
                key={row.id}
                row={row}
                isSelected={selectedWinner === row.id}
                onPick={() => onPick(row.id)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ExperimentRowView({ row, isSelected, onPick }: {
  row: ExperimentRow; isSelected: boolean; onPick: () => void;
}) {
  const k = row.kpis;
  const ret = k?.total_return_pct;
  const sharpe = ret != null && k?.max_drawdown_pct ? ret / Math.abs(k.max_drawdown_pct) : null;
  return (
    <tr className={isSelected ? "slab-table__row--selected" : ""}>
      <td>{String(row.run_index).padStart(3, "0")}</td>
      <td>{row.start_date?.slice(0, 10) ?? "—"}</td>
      <td className="slab-table__num" style={{ color: ret != null && ret >= 0 ? "var(--slab-terminal)" : "var(--slab-rose)" }}>
        {ret != null ? `${ret >= 0 ? "+" : ""}${ret.toFixed(1)}%` : "—"}
      </td>
      <td className="slab-table__num">{k?.alpha_pct != null ? `${k.alpha_pct >= 0 ? "+" : ""}${k.alpha_pct.toFixed(1)}%` : "—"}</td>
      <td className="slab-table__num">{k?.win_rate != null ? `${k.win_rate.toFixed(1)}%` : "—"}</td>
      <td className="slab-table__num">{k?.profit_factor != null ? k.profit_factor.toFixed(2) : "—"}</td>
      <td className="slab-table__num">{k?.total_trades ?? "—"}</td>
      <td className="slab-table__num">{sharpe != null ? sharpe.toFixed(2) : "—"}</td>
      <td>
        {row.status === "completed" ? (
          <span className="slab-tag slab-tag--terminal">OK</span>
        ) : (
          <span className="slab-tag slab-tag--rose" title={row.error_message ?? ""}>FAIL</span>
        )}
      </td>
      <td>
        {row.status === "completed" && (
          <button
            type="button"
            onClick={onPick}
            className={`slab-btn slab-btn--xs ${isSelected ? "slab-btn--primary" : ""}`}
          >
            {isSelected ? "✓ Winner" : "Pick"}
          </button>
        )}
      </td>
    </tr>
  );
}

function useMemoSortByIndex(rows: ExperimentRow[]) {
  return useMemo(() => rows.slice().sort((a, b) => a.run_index - b.run_index), [rows]);
}

// ── Post-batch actions ────────────────────────────────────────────────
function PostBatchActions(props: {
  onSummarize: () => void; isSummarizing: boolean;
  onRefine: () => void; isRefining: boolean;
  onAnotherBatch: () => void;
  summary: SummarizeResponse | null;
  refine: RefineStrategyResponse | null;
  onAcceptRefine: (diff: string) => void; onRejectRefine: () => void;
  isApplying: boolean;
}) {
  return (
    <div style={{ maxWidth: 1280, marginTop: 32, display: "flex", flexDirection: "column", gap: 24 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className="slab-eyebrow">// After batch</span>
        <div style={{ flex: 1 }} />
        <button
          type="button"
          onClick={props.onSummarize}
          disabled={props.isSummarizing}
          className="slab-btn"
        >
          <Sparkles size={11} />
          {props.isSummarizing ? "Analyzing…" : "AI summary"}
        </button>
        <button
          type="button"
          onClick={props.onRefine}
          disabled={props.isRefining}
          className="slab-btn"
        >
          <Sparkles size={11} />
          {props.isRefining ? "Refining…" : "Refine strategy"}
        </button>
        <button
          type="button"
          onClick={props.onAnotherBatch}
          className="slab-btn slab-btn--ghost"
        >
          <RotateCcw size={11} />
          New batch
        </button>
      </div>

      <AnimatePresence>
        {props.summary && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="slab-panel"
          >
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold">
                <FileText size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
                AI summary
              </span>
              <span className="slab-mono slab-mono--xs slab-mono--dim">3 paragraphs</span>
            </div>
            <div className="slab-panel__body">
              <p className="slab-prose" style={{ whiteSpace: "pre-wrap" }}>
                {props.summary.summary_text}
              </p>
            </div>
          </motion.div>
        )}

        {props.refine && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="slab-panel"
          >
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold">// Suggested change</span>
              <span className="slab-mono slab-mono--xs slab-mono--dim">
                review before applying
              </span>
            </div>
            <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              <p className="slab-prose">{props.refine.rationale}</p>
              <DiffReview
                diff={props.refine.diff}
                summary={props.refine.summary}
                onAccept={() => props.onAcceptRefine(props.refine!.diff)}
                onReject={props.onRejectRefine}
                isApplying={props.isApplying}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
