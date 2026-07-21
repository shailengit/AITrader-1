import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { strategyLabApi } from "../../lib/strategyLab";
import { ModelPicker } from "../../components/strategy-lab/ModelPicker";

interface StepIdeaProps {
  onCreated: (sessionId: string) => void;
  defaultModel?: string;
}

const DEFAULT_MODEL = "deepseek-v4-flash:cloud";

export function StepIdea({ onCreated, defaultModel = DEFAULT_MODEL }: StepIdeaProps) {
  const [prompt, setPrompt] = useState("");
  const [name, setName] = useState("");
  const [model, setModel] = useState(defaultModel);
  const qc = useQueryClient();

  const create = useMutation({
    mutationFn: () =>
      strategyLabApi.createSession({
        name: name.trim() || autoName(prompt),
        prompt: prompt.trim(),
        model_id: model,
      }),
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["strategy-lab-sessions"] });
      onCreated(session.id);
    },
  });

  const canSubmit = prompt.trim().length > 0 && !create.isPending;

  return (
    <div className="space-y-6 p-6">
      <header>
        <h2 className="text-xl font-semibold text-zinc-100">1. Describe your strategy idea</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Write the strategy in natural language. The LLM will plan and code it for you.
        </p>
      </header>

      <div>
        <label className="mb-2 block text-sm font-medium text-zinc-300">
          Session name (optional)
        </label>
        <input
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder={autoName(prompt) || "My strategy"}
          className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 text-sm text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-zinc-300">
          Strategy description
        </label>
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={6}
          placeholder="e.g. Buy stocks where EMA20 crosses above EMA200. Rank by crossover angle + market cap. Hold top 5, exit on death cross or 20% trailing stop."
          className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-sm text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div>
        <label className="mb-2 block text-sm font-medium text-zinc-300">Model</label>
        <ModelPicker value={model} onChange={setModel} disabled={create.isPending} />
      </div>

      <div className="flex items-center gap-3">
        <Button onClick={() => create.mutate()} disabled={!canSubmit}>
          {create.isPending ? "Creating..." : "Create session →"}
        </Button>
        {create.isError && (
          <span className="text-sm text-red-400">
            {String((create.error as Error)?.message ?? "Failed to create session")}
          </span>
        )}
      </div>
    </div>
  );
}

function autoName(prompt: string): string {
  const trimmed = prompt.trim();
  if (!trimmed) return "";
  return trimmed.slice(0, 60) + (trimmed.length > 60 ? "..." : "");
}
