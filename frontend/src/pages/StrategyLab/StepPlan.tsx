import { useState, useEffect } from "react";
import { useMutation } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { strategyLabApi, type StrategySession } from "../../lib/strategyLab";

interface StepPlanProps {
  session: StrategySession;
  model: string;
  onPlanApproved: () => void;
}

export function StepPlan({ session, model, onPlanApproved }: StepPlanProps) {
  const [planText, setPlanText] = useState(session.plan_text ?? "");

  // Generate plan on mount if not present
  const generate = useMutation({
    mutationFn: () => strategyLabApi.generatePlan(session.id, { model }),
    onSuccess: (r) => setPlanText(r.plan_text),
  });

  useEffect(() => {
    if (!session.plan_text && !generate.isPending && !generate.isError) {
      generate.mutate();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session.id]);

  // Save edited plan
  const save = useMutation({
    mutationFn: () => strategyLabApi.updateSession(session.id, { plan_text: planText }),
  });

  return (
    <div className="space-y-6 p-6">
      <header>
        <h2 className="text-xl font-semibold text-zinc-100">2. Review the plan</h2>
        <p className="mt-1 text-sm text-zinc-400">
          The LLM's structured plan for your strategy. Edit it if needed, then approve.
        </p>
      </header>

      {generate.isPending && (
        <div className="rounded-lg border border-zinc-700 bg-zinc-900/30 p-8 text-center">
          <div className="text-sm text-zinc-300">Generating plan…</div>
          <div className="mt-1 text-xs text-zinc-500">This usually takes 5-15 seconds.</div>
        </div>
      )}

      {generate.isError && (
        <div className="rounded-lg border border-red-800 bg-red-950/30 p-4 text-sm text-red-300">
          Failed to generate plan: {String((generate.error as Error)?.message ?? "unknown error")}
          <button
            onClick={() => generate.mutate()}
            className="ml-3 underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      )}

      {planText && !generate.isPending && (
        <>
          <div>
            <label className="mb-2 block text-sm font-medium text-zinc-300">
              Plan (edit if you want to steer the LLM)
            </label>
            <textarea
              value={planText}
              onChange={(e) => setPlanText(e.target.value)}
              rows={18}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 font-mono text-sm text-zinc-100 focus:border-blue-500 focus:outline-none"
            />
          </div>

          <div className="flex items-center gap-3">
            <Button
              onClick={() => save.mutate()}
              disabled={save.isPending || planText === session.plan_text}
              variant="secondary"
            >
              {save.isPending ? "Saving…" : "Save edits"}
            </Button>
            <Button onClick={onPlanApproved} disabled={!planText.trim()}>
              Approve &amp; Generate Code →
            </Button>
            {save.isSuccess && (
              <span className="text-xs text-emerald-400">Saved</span>
            )}
            <button
              onClick={() => generate.mutate()}
              className="ml-2 text-sm text-zinc-500 underline hover:text-zinc-300"
            >
              Regenerate
            </button>
          </div>
        </>
      )}
    </div>
  );
}
