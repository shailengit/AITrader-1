import { useState, useEffect, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, RefreshCw, FileText } from "lucide-react";
import { strategyLabApi, type StrategySession } from "../../lib/strategyLab";

interface StepPlanProps {
  session: StrategySession;
  model: string;
  onPlanApproved: () => void;
}

export function StepPlan({ session, model, onPlanApproved }: StepPlanProps) {
  const [planText, setPlanText] = useState(session.plan_text ?? "");
  const qc = useQueryClient();

  const generate = useMutation({
    mutationFn: () => strategyLabApi.generatePlan(session.id, { model }),
    onSuccess: (r) => {
      setPlanText(r.plan_text);
      // Invalidate the session query so the next mount of StepPlan sees
      // the populated plan_text and does NOT re-fire generation.
      qc.invalidateQueries({ queryKey: ["strategy-lab-session", session.id] });
    },
  });

  // Derive a stable "phase" string from local state instead of mutation
  // flags. We tried `generate.isPending` directly, but a re-render between
  // onSuccess and the mutation's state update left `isPending` reporting
  // `true` indefinitely even after the plan had arrived and `planText` was
  // set. Checking `planText` first means a successful plan takes priority
  // over a stale "still pending" flag.
  const phase: "drafting" | "ready" | "waiting" | "error" = planText
    ? "ready"
    : generate.isError
      ? "error"
      : generate.isPending
        ? "drafting"
        : "waiting";

  // Auto-generate the plan once per session.id. We use a ref to guarantee
  // we only fire once per component instance even if the parent re-renders
  // the step subtree (the previous design fired a duplicate POST on every
  // re-mount, generating two parallel LLM calls). The `onSuccess` invalidates
  // the session query, so subsequent mounts will see the populated
  // plan_text and skip the call.
  const attemptedRef = useRef(false);
  useEffect(() => {
    if (attemptedRef.current) return;
    if (session.plan_text) {
      // Already have a plan — nothing to do
      attemptedRef.current = true;
      return;
    }
    if (generate.isPending) {
      attemptedRef.current = true;
      return;
    }
    attemptedRef.current = true;
    generate.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]);

  const save = useMutation({
    mutationFn: () => strategyLabApi.updateSession(session.id, { plan_text: planText }),
  });

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// 02 · Plan</div>
          <h1 className="slab-page-head__title">Read the plan.</h1>
          <p className="slab-page-head__lede">
            The LLM turned your prompt into a structured strategy plan. Edit
            it if you want to steer the next step, then approve.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Phase · Review</span>
          <span
            className={
              phase === "drafting"
                ? "slab-status slab-status--live"
                : phase === "ready"
                  ? "slab-status slab-status--gold"
                  : phase === "error"
                    ? "slab-status slab-status--error"
                    : "slab-status slab-status--dim"
            }
          >
            <span className="slab-status__dot" />
            {phase === "drafting" ? "DRAFTING" : phase === "ready" ? "DRAFT READY" : phase === "error" ? "ERROR" : "WAITING"}
          </span>
        </div>
      </div>

      <div className="slab-page-body">
        {phase === "drafting" && <DraftingState />}
        {phase === "error" && (
          <div className="slab-panel">
            <div className="slab-panel__head">
              <span className="slab-eyebrow slab-eyebrow--gold" style={{ color: "var(--slab-rose)" }}>
                × Generation failed
              </span>
              <button onClick={() => generate.mutate()} className="slab-btn slab-btn--sm">
                <RefreshCw size={11} /> Retry
              </button>
            </div>
            <div className="slab-panel__body">
              <p className="slab-mono slab-mono--sm slab-mono--rose">
                {String((generate.error as Error)?.message ?? "Unknown error")}
              </p>
            </div>
          </div>
        )}

        {phase === "ready" && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            style={{ maxWidth: 920 }}
          >
            {/* Document-frame around the editor */}
            <div className="slab-corner-marks slab-panel" style={{ position: "relative" }}>
              <div className="slab-panel__head">
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <FileText size={12} style={{ color: "var(--slab-gold)" }} />
                  <span className="slab-eyebrow slab-eyebrow--gold">Plan · {session.id.slice(0, 8)}</span>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span className="slab-mono slab-mono--xs slab-mono--dim">editable</span>
                </div>
              </div>
              <textarea
                value={planText}
                onChange={(e) => setPlanText(e.target.value)}
                rows={22}
                className="slab-textarea"
                style={{
                  border: 0,
                  background: "transparent",
                  fontSize: 13,
                  lineHeight: 1.7,
                  padding: "20px 24px",
                  resize: "none",
                }}
              />
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 24 }}>
              <button
                type="button"
                onClick={() => save.mutate()}
                disabled={save.isPending || planText === session.plan_text}
                className="slab-btn"
              >
                {save.isPending ? "Saving…" : "Save edits"}
              </button>
              <button
                type="button"
                onClick={onPlanApproved}
                disabled={!planText.trim()}
                className="slab-btn slab-btn--primary"
              >
                Approve & generate code
                <ArrowRight size={12} />
              </button>
              <button
                type="button"
                onClick={() => generate.mutate()}
                className="slab-btn slab-btn--ghost"
                style={{ marginLeft: "auto" }}
              >
                <RefreshCw size={11} /> Regenerate
              </button>
              {save.isPending && <span className="slab-mono slab-mono--xs slab-mono--dim">saving…</span>}
              {save.isSuccess && <span className="slab-mono slab-mono--xs slab-mono--terminal">✓ saved</span>}
            </div>
          </motion.div>
        )}
      </div>
    </>
  );
}

function DraftingState() {
  // Live elapsed-time counter so the user knows the request is alive,
  // not stalled. Cloud model latencies for this prompt are typically
  // 15–30s end-to-end.
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const startedAt = Date.now();
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 250);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="slab-panel" style={{ maxWidth: 920, position: "relative" }}>
      <div className="slab-panel__head">
        <span className="slab-status slab-status--live">
          <span className="slab-status__dot" />
          Drafting plan
        </span>
        <span className="slab-mono slab-mono--xs slab-mono--dim">
          {elapsed}s · typical 15–30s
        </span>
      </div>
      <div style={{ padding: 32 }}>
        {/* Skeleton lines that look like the LLM is typing */}
        {[80, 60, 92, 45, 75, 88, 35, 70, 55].map((w, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0.15 }}
            animate={{ opacity: [0.15, 0.4, 0.15] }}
            transition={{ duration: 1.6, repeat: Infinity, delay: i * 0.08 }}
            style={{
              height: 10,
              width: `${w}%`,
              background: "var(--slab-rule)",
              marginBottom: 14,
            }}
          />
        ))}
      </div>
    </div>
  );
}
