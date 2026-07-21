import { useEffect, useState } from "react";
import { ChevronDown, Cloud, HardDrive } from "lucide-react";
import { strategyLabApi, type OllamaModel, type ModelVariant } from "../../lib/strategyLab";

interface ModelPickerProps {
  value: string; // model_id format: "deepseek-v4-flash:cloud"
  onChange: (modelId: string) => void;
  disabled?: boolean;
}

export function ModelPicker({ value, onChange, disabled }: ModelPickerProps) {
  const [models, setModels] = useState<OllamaModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    strategyLabApi
      .listModels()
      .then((m) => {
        if (mounted) {
          setModels(m);
          setLoading(false);
        }
      })
      .catch((e) => {
        if (mounted) {
          setError(String(e));
          setLoading(false);
        }
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading) {
    return <div className="text-sm text-zinc-400">Loading models...</div>;
  }
  if (error) {
    return <div className="text-sm text-red-400">Failed to load models: {error}</div>;
  }

  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className="w-full appearance-none rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2.5 pr-10 text-sm text-zinc-100 focus:border-blue-500 focus:outline-none disabled:opacity-50"
      >
        {models.map((m) =>
          m.variants.map((v) => {
            const id = formatModelId(m.id, v);
            return (
              <option key={id} value={id}>
                {m.id} : {v.name}
                {v.type === "cloud" ? " (cloud)" : " (local)"}
              </option>
            );
          })
        )}
      </select>
      <ChevronDown
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-zinc-500"
        size={16}
      />
      {value && <SelectedVariantBadge value={value} models={models} />}
    </div>
  );
}

function formatModelId(modelName: string, variant: ModelVariant): string {
  return `${modelName}:${variant.name}`;
}

function parseModelId(id: string): { name: string; variant: string } | null {
  const idx = id.indexOf(":");
  if (idx === -1) return null;
  return { name: id.slice(0, idx), variant: id.slice(idx + 1) };
}

function SelectedVariantBadge({ value, models }: { value: string; models: OllamaModel[] }) {
  const parsed = parseModelId(value);
  if (!parsed) return null;
  const model = models.find((m) => m.id === parsed.name);
  const variant = model?.variants.find((v) => v.name === parsed.variant);
  if (!variant) return null;
  const isCloud = variant.type === "cloud";
  return (
    <div className="mt-2 flex items-center gap-2 text-xs text-zinc-400">
      {isCloud ? <Cloud size={14} className="text-sky-400" /> : <HardDrive size={14} className="text-amber-400" />}
      <span>
        {isCloud
          ? "Cloud model — runs on Ollama's hosted inference"
          : "Local model — runs on this machine"}
      </span>
    </div>
  );
}
