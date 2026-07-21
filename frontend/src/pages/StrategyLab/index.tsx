import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { StepSidebar, type Step } from "../../components/strategy-lab/StepSidebar";
import { StepIdea } from "./StepIdea";
import { StepPlan } from "./StepPlan";
import { StepCode } from "./StepCode";
import { StepBacktest } from "./StepBacktest";
import { StepDeploy } from "./StepDeploy";
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
  const [selectedExperimentId, setSelectedExperimentId] = useState<string | null>(null);

  const session = useQuery({
    queryKey: ["strategy-lab-session", sessionId],
    queryFn: () => strategyLabApi.getSession(sessionId!),
    enabled: !!sessionId,
  });

  useEffect(() => {
    if (session.data && activeStep === 1) {
      setActiveStep(2);
    }
  }, [session.data, activeStep]);

  const handlePlanApproved = () => setActiveStep(3);
  const handleCodeReady = () => setActiveStep(4);
  const handleWinnerPicked = (experimentId: string) => {
    setSelectedExperimentId(experimentId);
    setActiveStep(5);
  };

  const handleCreated = (newSessionId: string) => {
    setSearchParams({ session: newSessionId });
  };

  const handleSelectStep = (stepId: number) => {
    if (!sessionId && stepId !== 1) return;
    if (stepId >= 3 && !session.data?.code_text) return;
    if (stepId >= 4 && !session.data?.code_text) return;
    setActiveStep(stepId);
  };

  const steps: Step[] = STEPS.map((s) => ({
    id: s.id,
    label: s.label,
    completed: sessionId
      ? s.id <= (session.data?.plan_text ? (session.data?.code_text ? 3 : 2) : 1)
      : false,
    active: s.id === activeStep,
  }));

  return (
    <div className="flex h-full min-h-[calc(100vh-4rem)]">
      <StepSidebar steps={steps} onSelect={handleSelectStep} />
      <main className="flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1280px]">
          {activeStep === 1 || !sessionId ? (
            <StepIdea onCreated={handleCreated} />
          ) : activeStep === 2 && session.data ? (
            <StepPlan
              session={session.data}
              model={session.data.model_id}
              onPlanApproved={handlePlanApproved}
            />
          ) : activeStep === 3 && session.data ? (
            <StepCode
              session={session.data}
              model={session.data.model_id}
              onCodeReady={handleCodeReady}
            />
          ) : activeStep === 4 && session.data ? (
            <StepBacktest
              session={session.data}
              onWinnerPicked={handleWinnerPicked}
            />
          ) : activeStep === 5 && session.data && selectedExperimentId ? (
            <StepDeploy
              session={session.data}
              experimentId={selectedExperimentId}
              onDeployed={() => {}}
            />
          ) : (
            <div className="space-y-6 p-6">
              <h2 className="text-xl font-semibold text-zinc-100">5. Deploy to Alpaca</h2>
              <div className="rounded-lg border border-dashed border-zinc-700 bg-zinc-900/30 p-8 text-center">
                <div className="text-sm text-zinc-300">No winner selected yet</div>
                <div className="mt-1 text-xs text-zinc-500">
                  Go back to Step 4 and click "pick" on a row to select the winner.
                </div>
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
