import { Check, Circle } from "lucide-react";

export interface Step {
  id: number;
  label: string;
  completed: boolean;
  active: boolean;
}

interface StepSidebarProps {
  steps: Step[];
  onSelect: (id: number) => void;
}

export function StepSidebar({ steps, onSelect }: StepSidebarProps) {
  return (
    <nav className="flex w-60 flex-col gap-1 border-r border-zinc-800 bg-zinc-900/50 p-4">
      <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider text-zinc-500">
        Steps
      </h2>
      {steps.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className={`flex items-center gap-3 rounded-md px-3 py-2 text-left text-sm transition-colors ${
            s.active
              ? "bg-zinc-800 text-zinc-100"
              : "text-zinc-400 hover:bg-zinc-800/50 hover:text-zinc-200"
          }`}
        >
          <div className="flex h-5 w-5 flex-shrink-0 items-center justify-center">
            {s.completed ? (
              <Check size={16} className="text-green-500" />
            ) : (
              <Circle
                size={16}
                className={s.active ? "text-blue-400" : "text-zinc-600"}
                fill={s.active ? "currentColor" : "none"}
              />
            )}
          </div>
          <div className="flex-1">
            <div className="font-medium">
              {s.id}. {s.label}
            </div>
          </div>
        </button>
      ))}
    </nav>
  );
}
