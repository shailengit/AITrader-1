import { useState, useEffect, useRef } from "react";
import { useMutation } from "@tanstack/react-query";
import Editor from "@monaco-editor/react";
import { Button } from "../../components/ui/Button";
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
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Sync to session's code when it loads
  useEffect(() => {
    if (session.code_text) setCode(session.code_text);
  }, [session.code_text]);

  // Debounced auto-save (1s)
  useEffect(() => {
    if (!session.code_text) return; // don't save the default placeholder
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      if (code !== session.code_text) {
        save.mutate();
      }
    }, 1000);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code]);

  // Generate code from plan
  const generate = useMutation({
    mutationFn: () => strategyLabApi.generateCode(session.id, { model }),
    onSuccess: (r) => setCode(r.code),
  });

  // Auto-save (separate hook so debounce effect can call it)
  const save = useMutation({
    mutationFn: () => strategyLabApi.updateSession(session.id, { code_text: code }),
  });

  // Generate a refinement diff
  const refine = useMutation({
    mutationFn: () =>
      strategyLabApi.refineCode(session.id, {
        model,
        current_code: code,
        instruction: refineInstruction,
      }),
    onSuccess: (r) => setPendingDiff({ diff: r.diff, summary: r.summary }),
  });

  // Apply the pending diff
  const apply = useMutation({
    mutationFn: (diff: string) =>
      strategyLabApi.applyDiff(session.id, { instruction: diff, current_code: code }),
    onSuccess: (r) => {
      setCode(r.code);
      setPendingDiff(null);
      setRefineInstruction("");
    },
  });

  return (
    <div className="space-y-6 p-6">
      <header>
        <h2 className="text-xl font-semibold text-zinc-100">3. Edit the strategy code</h2>
        <p className="mt-1 text-sm text-zinc-400">
          The LLM has written 4 filter functions + a StrategyConfig. Edit freely or ask
          the AI to refine.
        </p>
      </header>

      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <Editor
          height="500px"
          language="python"
          theme="vs-dark"
          value={code}
          onChange={(v) => setCode(v ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            tabSize: 4,
            wordWrap: "on",
            automaticLayout: true,
          }}
        />
      </div>

      <div className="flex items-center gap-3">
        {generate.isPending ? (
          <Button disabled>Generating code…</Button>
        ) : (
          <Button onClick={() => generate.mutate()} disabled={!session.plan_text}>
            {code === DEFAULT_CODE ? "Generate code" : "Regenerate code"}
          </Button>
        )}
        {save.isPending && <span className="text-xs text-zinc-400">Saving…</span>}
        {save.isSuccess && <span className="text-xs text-emerald-400">Saved</span>}
        {session.code_text && code !== DEFAULT_CODE && (
          <Button onClick={onCodeReady} variant="secondary">
            Run Backtest →
          </Button>
        )}
      </div>

      {/* Refinement panel */}
      {session.code_text && code !== DEFAULT_CODE && (
        <div className="space-y-3 rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
          <h3 className="text-sm font-semibold text-zinc-200">Refine with AI</h3>
          <p className="text-xs text-zinc-500">
            Tell the AI what to change (e.g. "widen trailing stop to 25%", "rank by RSI not market cap").
            It'll produce a diff you can review.
          </p>
          <textarea
            value={refineInstruction}
            onChange={(e) => setRefineInstruction(e.target.value)}
            rows={2}
            placeholder="What should change?"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
          />
          <Button
            onClick={() => refine.mutate()}
            disabled={!refineInstruction.trim() || refine.isPending}
          >
            {refine.isPending ? "Refining…" : "Generate diff"}
          </Button>
          {refine.isError && (
            <div className="text-sm text-red-400">
              {String((refine.error as Error)?.message ?? "Refine failed")}
            </div>
          )}

          {pendingDiff && (
            <div className="mt-3">
              <DiffReview
                diff={pendingDiff.diff}
                summary={pendingDiff.summary}
                onAccept={() => apply.mutate(pendingDiff.diff)}
                onReject={() => setPendingDiff(null)}
                isApplying={apply.isPending}
              />
              {apply.isError && (
                <div className="mt-2 text-sm text-red-400">
                  {String((apply.error as Error)?.message ?? "Apply failed")}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
