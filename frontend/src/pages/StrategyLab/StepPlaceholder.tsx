interface StepPlaceholderProps {
  stepNumber: number;
  title: string;
  comingIn: string; // e.g. "Phase 2", "Phase 3", etc.
  description: string;
}

export function StepPlaceholder({ stepNumber, title, comingIn, description }: StepPlaceholderProps) {
  return (
    <div className="space-y-6 p-6">
      <header>
        <h2 className="text-xl font-semibold text-zinc-100">
          {stepNumber}. {title}
        </h2>
        <p className="mt-1 text-sm text-zinc-400">{description}</p>
      </header>

      <div className="rounded-lg border border-dashed border-zinc-700 bg-zinc-900/30 p-8 text-center">
        <div className="text-sm font-medium text-zinc-300">Coming in {comingIn}</div>
        <div className="mt-1 text-xs text-zinc-500">
          This step will be implemented after Phase 1 is complete.
        </div>
      </div>
    </div>
  );
}
