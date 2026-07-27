import { useState, useEffect, useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, RefreshCw, FileText } from "lucide-react";
import { strategyLabApi, type StrategySession } from "../../lib/strategyLab";
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

interface StepPlanProps {
  session: StrategySession;
  model: string;
  onPlanApproved: () => void;
}

export function StepPlan({ session, model, onPlanApproved }: StepPlanProps) {
  const [planText, setPlanText] = useState(session.plan_text ?? "");
  // We tried using React Query's `generate.isPending` / `generate.isError`
  // directly, but in dev (StrictMode) the mutation observer can call
  // onError without triggering a re-render — leaving the page stuck on
  // DRAFTING. Tracking the status in local state with explicit setters
  // bypasses that and is reliable.
  const [status, setStatus] = useState<"drafting" | "ready" | "error" | "waiting">(
    session.plan_text ? "ready" : "waiting",
  );
  const [errorMsg, setErrorMsg] = useState<string>("");
  const qc = useQueryClient();

  const generate = useMutation({
    mutationFn: () => strategyLabApi.generatePlan(session.id, { model }),
    onSuccess: (r) => {
      if (r.error) {
        setStatus("error");
        setErrorMsg(r.error);
        return;
      }
      setPlanText(r.plan_text);
      setStatus("ready");
      setErrorMsg("");
      // Invalidate the session query so the next mount of StepPlan sees
      // the populated plan_text and does NOT re-fire generation.
      qc.invalidateQueries({ queryKey: ["strategy-lab-session", session.id] });
    },
    onError: (e: unknown) => {
      setStatus("error");
      // Parse the fetch error. The backend returns one of:
      //   { "detail": "..." }                                          — string detail
      //   { "detail": { "error": "...", "details": "..." } }          — nested object
      // The postJson wrapper adds another layer: err.detail is the body,
      // so we have err.detail.detail.{error,details} for the nested case.
      const err = e as { detail?: unknown; message?: string };
      let msg = err.message ?? "Generation failed";
      let d: unknown = err.detail;
      // Unwrap if the body itself is a {detail: ...} wrapper
      if (typeof d === "object" && d !== null && "detail" in (d as object)) {
        d = (d as { detail: unknown }).detail;
      }
      if (typeof d === "object" && d !== null) {
        const obj = d as { details?: string; error?: string };
        if (obj.details) msg = obj.details;
        else if (obj.error) msg = obj.error;
      } else if (typeof d === "string") {
        msg = d;
      }
      setErrorMsg(msg);
    },
  });

  // For backwards compat: derive a phase string. With local `status`,
  // the values are mutually exclusive and update synchronously.
  const phase = status;

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
      setStatus("ready");
      return;
    }
    if (generate.isPending) {
      attemptedRef.current = true;
      return;
    }
    attemptedRef.current = true;
    setStatus("drafting");
    setErrorMsg("");
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
              <span className="slab-status slab-status--error">
                <span className="slab-status__dot" />
                Generation failed
              </span>
              <button
                onClick={() => {
                  setStatus("drafting");
                  setErrorMsg("");
                  generate.mutate();
                }}
                className="slab-btn slab-btn--sm"
              >
                <RefreshCw size={11} /> Retry
              </button>
            </div>
            <div className="slab-panel__body">
              <p
                className="slab-mono slab-mono--sm slab-mono--rose"
                style={{ wordBreak: "break-word", whiteSpace: "pre-wrap" }}
              >
                {errorMsg || "Unknown error"}
              </p>
              <p className="slab-field__hint" style={{ marginTop: 12 }}>
                The LLM service returned an error. Common causes: the chosen
                model is unavailable on the Ollama cloud, the response was
                truncated (the prompt is too large for the model's
                max_tokens), or the model returned an empty result. Try a
                different model from the model picker, or click Retry.
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

            {/* ChatPanel */}
            <ChatPanel
              sessionId={session.id}
              defaultModelId={session.model_id}
            />
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
