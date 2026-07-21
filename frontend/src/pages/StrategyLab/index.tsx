import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { StepSidebar, type Step } from "../../components/strategy-lab/StepSidebar";
import { StepIdea } from "./StepIdea";
import { StepPlaceholder } from "./StepPlaceholder";
import { strategyLabApi } from "../../lib/strategyLab";

const STEPS: { id: number; label: string; comingIn: string; description: string }[] = [
  { id: 1, label: "Idea", comingIn: "Phase 1", description: "Describe your strategy in natural language" },
  { id: 2, label: "Plan", comingIn: "Phase 2", description: "Review the LLM's structured plan" },
  { id: 3, label: "Code", comingIn: "Phase 2", description: "Edit the generated strategy code" },
  { id: 4, label: "Backtest", comingIn: "Phase 3", description: "Run experiments with randomized time windows" },
  { id: 5, label: "Deploy", comingIn: "Phase 4", description: "Deploy the winning strategy to Alpaca" },
];

export default function StrategyLabPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const sessionId = searchParams.get("session");
  const [activeStep, setActiveStep] = useState<number>(1);

  // If no session, default to Step 1. If session exists, allow step navigation.
  const session = useQuery({
    queryKey: ["strategy-lab-session", sessionId],
    queryFn: () => strategyLabApi.getSession(sessionId!),
    enabled: !!sessionId,
  });

  useEffect(() => {
    // When a session loads, jump to its "current" step (Phase 1: always Step 2 once created)
    if (session.data) {
      setActiveStep(2);
    }
  }, [session.data]);

  const handleCreated = (newSessionId: string) => {
    setSearchParams({ session: newSessionId });
  };

  const handleSelectStep = (stepId: number) => {
    if (!sessionId && stepId !== 1) {
      // Can't go past Step 1 without a session
      return;
    }
    setActiveStep(stepId);
  };

  const steps: Step[] = STEPS.map((s) => ({
    id: s.id,
    label: s.label,
    completed: sessionId
      ? s.id === 1
      : false, // Phase 1: only step 1 is "completable"
    active: s.id === activeStep,
  }));

  return (
    <div className="flex h-full min-h-[calc(100vh-4rem)]">
      <StepSidebar steps={steps} onSelect={handleSelectStep} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1024px]">
          {activeStep === 1 || !sessionId ? (
            <StepIdea onCreated={handleCreated} />
          ) : activeStep === 2 ? (
            <StepPlaceholder
              stepNumber={2}
              title={STEPS[1].label}
              comingIn={STEPS[1].comingIn}
              description={`Session created: ${session.data?.name ?? ""} (id ${sessionId?.slice(0, 8)}...).`}
            />
          ) : activeStep === 3 ? (
            <StepPlaceholder
              stepNumber={3}
              title={STEPS[2].label}
              comingIn={STEPS[2].comingIn}
              description={STEPS[2].description}
            />
          ) : activeStep === 4 ? (
            <StepPlaceholder
              stepNumber={4}
              title={STEPS[3].label}
              comingIn={STEPS[3].comingIn}
              description={STEPS[3].description}
            />
          ) : (
            <StepPlaceholder
              stepNumber={5}
              title={STEPS[4].label}
              comingIn={STEPS[4].comingIn}
              description={STEPS[4].description}
            />
          )}
        </div>
      </main>
    </div>
  );
}
