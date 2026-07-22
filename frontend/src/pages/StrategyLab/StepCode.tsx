import { useState, useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import Editor from "@monaco-editor/react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowRight, Wand2, FileCode, Save, RefreshCw, AlertCircle } from "lucide-react";
import { DiffReview } from "../../components/strategy-lab/DiffReview";
import { strategyLabApi, type StrategySession } from "../../lib/strategyLab";

interface StepCodeProps {
  session: StrategySession;
  model: string;
  onCodeReady: () => void;
}

const DEFAULT_CODE = `# (LLM has not generated code yet — click "Generate Code" below)`;

export function StepCode({ session, model, onCodeReady }: StepCodeProps) {
  const [code, setCode] = useState(session.code_text ?? DEFAULT_CODE);
  const [refineInstruction, setRefineInstruction] = useState("");
  const [pendingDiff, setPendingDiff] = useState<{ diff: string; summary: string } | null>(null);
  const [showRefine, setShowRefine] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (session.code_text) setCode(session.code_text);
  }, [session.code_text]);

  useEffect(() => {
    if (!session.code_text) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (code !== session.code_text) save.mutate();
    }, 1000);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  const generate = useMutation({
    mutationFn: () => strategyLabApi.generateCode(session.id, { model }),
    onSuccess: (r) => setCode(r.code),
  });

  const save = useMutation({
    mutationFn: () => strategyLabApi.updateSession(session.id, { code_text: code }),
  });

  const refine = useMutation({
    mutationFn: () =>
      strategyLabApi.refineCode(session.id, {
        model,
        current_code: code,
        instruction: refineInstruction,
      }),
    onSuccess: (r) => setPendingDiff({ diff: r.diff, summary: r.summary }),
  });

  const apply = useMutation({
    mutationFn: (diff: string) =>
      strategyLabApi.applyDiff(session.id, { instruction: diff, current_code: code }),
    onSuccess: (r) => {
      setCode(r.code);
      setPendingDiff(null);
      setRefineInstruction("");
      setShowRefine(false);
    },
  });

  const isDirty = code !== (session.code_text ?? DEFAULT_CODE) && code !== DEFAULT_CODE;
  const isInitialState = code === DEFAULT_CODE;

  // Live timer so the user knows the request is alive during the 30-90s
  // the LLM takes to write the strategy code (or fails).
  const [codeElapsed, setCodeElapsed] = useState(0);
  useEffect(() => {
    if (!generate.isPending && !refine.isPending) return;
    const startedAt = Date.now();
    setCodeElapsed(0);
    const id = setInterval(() => setCodeElapsed(Math.floor((Date.now() - startedAt) / 1000)), 250);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [generate.isPending, refine.isPending]);

  // Build a synthetic class file name from the session name
  const fileName = (session.name || "strategy")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .slice(0, 32) + ".py";

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// 03 · Code</div>
          <h1 className="slab-page-head__title">Edit the strategy.</h1>
          <p className="slab-page-head__lede">
            Four filter functions plus a <span className="slab-mono">StrategyConfig</span>.
            Edit freely or ask the AI to refine.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Phase · Edit</span>
          <span className="slab-mono slab-mono--gold">
            {save.isPending ? "SAVING…" : isDirty ? "UNSAVED" : "SAVED"}
          </span>
        </div>
      </div>

      <div className="slab-page-body">
        {/* File-tab header above the editor */}
        <div
          className="slab-panel"
          style={{ position: "relative", maxWidth: 1280 }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              padding: "8px 12px",
              background: "var(--slab-ink-3)",
              borderBottom: "1px solid var(--slab-rule)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <FileCode size={12} style={{ color: "var(--slab-gold)" }} />
              <span className="slab-mono slab-mono--sm">{fileName}</span>
              {isDirty && (
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 0,
                    background: "var(--slab-gold)",
                    display: "inline-block",
                  }}
                  title="Unsaved changes"
                />
              )}
            </div>
            <div className="slab-mono slab-mono--xs slab-mono--faint">
              python · 4 spaces · unix lf
            </div>
          </div>

          <div style={{ background: "var(--slab-ink-2)" }}>
            <Editor
              height="540px"
              language="python"
              theme="vs-dark"
              value={code}
              onChange={(v) => setCode(v ?? "")}
              options={{
                minimap: { enabled: false },
                fontSize: 13,
                fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
                tabSize: 4,
                wordWrap: "on",
                automaticLayout: true,
                lineNumbers: "on",
                renderLineHighlight: "gutter",
                scrollBeyondLastLine: false,
                padding: { top: 16, bottom: 16 },
              }}
            />
          </div>
        </div>

        {/* Action row */}
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 20, maxWidth: 1280, flexWrap: "wrap" }}>
          {generate.isPending ? (
            <span className="slab-status slab-status--live">
              <span className="slab-status__dot" />
              Generating code
              <span className="slab-mono slab-mono--xs slab-mono--dim" style={{ marginLeft: 12 }}>
                {codeElapsed}s · typical 30–60s
              </span>
            </span>
          ) : (
            <button
              type="button"
              onClick={() => generate.mutate()}
              disabled={!session.plan_text}
              className="slab-btn"
            >
              <RefreshCw size={11} />
              {isInitialState ? "Generate code" : "Regenerate code"}
            </button>
          )}

          {save.isPending && (
            <span className="slab-mono slab-mono--xs slab-mono--dim">
              <Save size={10} style={{ verticalAlign: "middle", marginRight: 4 }} />
              saving
            </span>
          )}
          {save.isSuccess && !isDirty && (
            <span className="slab-mono slab-mono--xs slab-mono--terminal">✓ saved</span>
          )}

          {!isInitialState && (
            <button
              type="button"
              onClick={() => setShowRefine(!showRefine)}
              className={`slab-btn ${showRefine ? "slab-btn--primary" : ""}`}
              style={{ marginLeft: 12 }}
            >
              <Wand2 size={11} />
              Refine with AI
            </button>
          )}

          {!isInitialState && (
            <button
              type="button"
              onClick={onCodeReady}
              className="slab-btn slab-btn--terminal"
              style={{ marginLeft: "auto" }}
            >
              Run backtest
              <ArrowRight size={12} />
            </button>
          )}
        </div>

        {/* Generation error — only shown when generate mutation has failed. */}
        {generate.isError && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="slab-panel"
            style={{ maxWidth: 1280, marginTop: 16, position: "relative" }}
          >
            <div className="slab-panel__head">
              <span className="slab-status slab-status--error">
                <span className="slab-status__dot" />
                Code generation failed
              </span>
              <button
                type="button"
                onClick={() => generate.mutate()}
                className="slab-btn slab-btn--sm"
              >
                <RefreshCw size={11} /> Retry
              </button>
            </div>
            <div className="slab-panel__body">
              <p className="slab-mono slab-mono--sm slab-mono--rose" style={{ wordBreak: "break-word" }}>
                {extractErrorMessage(generate.error)}
              </p>
              <p className="slab-field__hint" style={{ marginTop: 12 }}>
                The model returned a 502 from the LLM provider. Common causes:
                the chosen model is unavailable on the Ollama cloud, the
                response was truncated (the prompt is large), or the model
                returned an empty result. Try a different model, or click
                Retry to attempt again.
              </p>
            </div>
          </motion.div>
        )}

        {/* Refine panel (toggled) */}
        <AnimatePresence>
          {showRefine && !isInitialState && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ duration: 0.2 }}
              style={{ overflow: "hidden", marginTop: 16, maxWidth: 1280 }}
            >
              <div className="slab-panel">
                <div className="slab-panel__head">
                  <span className="slab-eyebrow slab-eyebrow--gold">// Refine</span>
                  <span className="slab-mono slab-mono--xs slab-mono--dim">
                    LLM returns a diff for review
                  </span>
                </div>
                <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                  <textarea
                    value={refineInstruction}
                    onChange={(e) => setRefineInstruction(e.target.value)}
                    rows={3}
                    placeholder="widen trailing stop to 25%"
                    className="slab-textarea"
                  />
                  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                    <button
                      type="button"
                      onClick={() => refine.mutate()}
                      disabled={!refineInstruction.trim() || refine.isPending}
                      className="slab-btn slab-btn--primary"
                    >
                      {refine.isPending ? "Drafting diff…" : "Generate diff"}
                    </button>
                    {refine.isError && (
                      <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <AlertCircle size={12} />
                        {String((refine.error as Error)?.message ?? "Refine failed")}
                      </span>
                    )}
                  </div>

                  {pendingDiff && (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                    >
                      <DiffReview
                        diff={pendingDiff.diff}
                        summary={pendingDiff.summary}
                        onAccept={() => apply.mutate(pendingDiff.diff)}
                        onReject={() => setPendingDiff(null)}
                        isApplying={apply.isPending}
                      />
                      {apply.isError && (
                        <div className="slab-mono slab-mono--sm slab-mono--rose" style={{ marginTop: 8 }}>
                          × {String((apply.error as Error)?.message ?? "Apply failed")}
                        </div>
                      )}
                    </motion.div>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </>
  );
}

// Parse a FastAPI error response into a user-friendly string.
// Backend shapes:
//   { detail: "..." }                                            — string
//   { detail: { error: "...", details: "..." } }                — nested
// postJson wraps the body in err.detail, so we have err.detail.detail for
// the nested case.
function extractErrorMessage(err: unknown): string {
  if (!err) return "Unknown error";
  const e = err as { message?: string; detail?: unknown };
  // Unwrap if the body itself is a {detail: ...} wrapper
  let d: unknown = e.detail;
  if (typeof d === "object" && d !== null && "detail" in (d as object)) {
    d = (d as { detail: unknown }).detail;
  }
  if (typeof d === "object" && d !== null) {
    const obj = d as { details?: string; error?: string };
    if (obj.details) return obj.details;
    if (obj.error) return obj.error;
  }
  if (typeof d === "string") return d;
  if (e.message) return e.message;
  return String(err);
}
