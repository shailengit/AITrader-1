import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { StepSidebar } from "../../components/strategy-lab/StepSidebar";
import { StepIdea } from "./StepIdea";
import { StepPlan } from "./StepPlan";
import { StepCode } from "./StepCode";
import { StepBacktest } from "./StepBacktest";
import { StepDeploy } from "./StepDeploy";
import { strategyLabApi } from "../../lib/strategyLab";
import "../../components/strategy-lab/lab.css";

const STEPS = [
  { id: 1, label: "Idea", meta: "Prompt" },
  { id: 2, label: "Plan", meta: "Review" },
  { id: 3, label: "Code", meta: "Edit" },
  { id: 4, label: "Backtest", meta: "Validate" },
  { id: 5, label: "Deploy", meta: "Ship" },
] as const;

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
    setActiveStep(stepId);
  };

  const completedUpTo = sessionId
    ? session.data?.plan_text
      ? session.data?.code_text
        ? 3
        : 2
      : 1
    : 0;

  return (
    <div className="slab flex h-full min-h-[calc(100vh-4rem)]">
      <StepSidebar
        steps={STEPS.map((s) => ({
          id: s.id,
          label: s.label,
          meta: s.meta,
          completed: s.id <= completedUpTo,
          active: s.id === activeStep,
        }))}
        onSelect={handleSelectStep}
        sessionName={session.data?.name}
        modelId={session.data?.model_id}
      />
      <main className="flex-1 overflow-y-auto">
        <motion.div
          key={activeStep}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
        >
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
            <StepNoWinner />
          )}
        </motion.div>
      </main>
    </div>
  );
}

function StepNoWinner() {
  return (
    <div className="slab-page-body">
      <div className="slab-eyebrow slab-eyebrow--gold mb-3">// 05 · Deploy</div>
      <h1 className="slab-display slab-h2 mb-3">Pick a winner first.</h1>
      <p className="slab-lede">
        You haven't selected a winning experiment yet. Go back to step 4 and
        click <span className="slab-mono slab-mono--gold">PICK</span> on the
        row with the best metrics.
      </p>
    </div>
  );
}
