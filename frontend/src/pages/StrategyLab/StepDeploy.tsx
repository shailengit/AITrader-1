import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, AnimatePresence } from "framer-motion";
import { Rocket, Check, X, AlertCircle, History, FileCode, RotateCcw } from "lucide-react";
import { strategyLabApi, type StrategySession } from "../../lib/strategyLab";
import { ChatPanel } from "../../components/strategy-lab/ChatPanel";

interface StepDeployProps {
  session: StrategySession;
  experimentId: string;
  onDeployed: () => void;
}

export function StepDeploy({ session, experimentId, onDeployed }: StepDeployProps) {
  const [className, setClassName] = useState("");
  const [confirmOpen, setConfirmOpen] = useState(false);
  const qc = useQueryClient();

  const deployMut = useMutation({
    mutationFn: () =>
      strategyLabApi.deploy(session.id, {
        experiment_id: experimentId,
        class_name: className.trim() || undefined,
      }),
    onSuccess: (deployment) => {
      qc.invalidateQueries({ queryKey: ["strategy-lab-deployments"] });
      onDeployed();
      // eslint-disable-next-line no-console
      console.log("Deployed", deployment.class_name);
    },
  });

  const deployments = useQuery({
    queryKey: ["strategy-lab-deployments"],
    queryFn: () => strategyLabApi.listDeployments(),
  });

  const rollback = useMutation({
    mutationFn: (deploymentId: string) => strategyLabApi.rollbackDeployment(deploymentId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["strategy-lab-deployments"] });
    },
  });

  return (
    <>
      <div className="slab-page-head">
        <div>
          <div className="slab-eyebrow slab-eyebrow--gold">// 05 · Deploy</div>
          <h1 className="slab-page-head__title">Ship to paper.</h1>
          <p className="slab-page-head__lede">
            Promote the winning experiment to a live Strategy class on the
            Alpaca paper account. Previous deployments are deactivated and
            can be rolled back.
          </p>
        </div>
        <div className="slab-page-head__meta">
          <span>Phase · Ship</span>
          <span className="slab-mono slab-mono--gold">READY</span>
        </div>
      </div>

      <div className="slab-page-body">
        {/* Selected experiment summary */}
        <div className="slab-corner-marks slab-panel" style={{ maxWidth: 920, position: "relative" }}>
          <div className="slab-panel__head">
            <span className="slab-eyebrow slab-eyebrow--gold">// Selected experiment</span>
            <span className="slab-mono slab-mono--xs slab-mono--dim">id · {experimentId.slice(0, 8)}</span>
          </div>
          <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            <div className="slab-field">
              <label className="slab-field__label">Class name</label>
              <input
                type="text"
                value={className}
                onChange={(e) => setClassName(e.target.value)}
                placeholder="auto · derived from session name + as-of date"
                className="slab-input"
              />
              <div className="slab-field__hint">
                A valid Python identifier. Leave blank to use the auto-generated name.
              </div>
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
                padding: 14,
                background: "var(--slab-ink-3)",
                border: "1px solid var(--slab-rule)",
              }}
            >
              <div>
                <div className="slab-eyebrow">Target</div>
                <div className="slab-mono slab-mono--md slab-mono--gold" style={{ marginTop: 4 }}>
                  📄 Paper account
                </div>
              </div>
              <div>
                <div className="slab-eyebrow">Side effects</div>
                <div className="slab-mono slab-mono--md slab-mono--dim" style={{ marginTop: 4 }}>
                  writes 1 file · updates runner import
                </div>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <button
                type="button"
                onClick={() => setConfirmOpen(true)}
                disabled={deployMut.isPending}
                className="slab-btn slab-btn--terminal"
                style={{ padding: "12px 24px" }}
              >
                <Rocket size={12} />
                {deployMut.isPending ? "Deploying…" : "Deploy to paper"}
              </button>
              {deployMut.isError && (
                <span className="slab-mono slab-mono--sm slab-mono--rose" style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <AlertCircle size={12} />
                  {String((deployMut.error as Error)?.message ?? "Deploy failed")}
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Deploy result */}
        <AnimatePresence>
          {deployMut.isSuccess && deployMut.data && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="slab-corner-marks slab-panel"
              style={{ maxWidth: 920, marginTop: 24, position: "relative" }}
            >
              <div className="slab-panel__head">
                <span className="slab-eyebrow slab-eyebrow--gold">// Live</span>
                <span className="slab-status slab-status--terminal">
                  <span className="slab-status__dot" />
                  Deployed
                </span>
              </div>
              <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <div>
                  <div className="slab-eyebrow">Class</div>
                  <div className="slab-mono slab-mono--xl slab-mono--terminal" style={{ marginTop: 4 }}>
                    {deployMut.data.class_name}
                  </div>
                </div>
                <div>
                  <div className="slab-eyebrow">File path</div>
                  <div className="slab-mono slab-mono--md slab-mono--dim" style={{ marginTop: 4 }}>
                    <FileCode size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
                    {deployMut.data.class_file_path}
                  </div>
                </div>
                <div>
                  <div className="slab-eyebrow">Verification</div>
                  <div style={{ display: "flex", gap: 8, marginTop: 8, flexWrap: "wrap" }}>
                    {Object.entries(deployMut.data.verification ?? {}).map(([k, v]) => (
                      <span
                        key={k}
                        className={`slab-tag ${v ? "slab-tag--terminal" : "slab-tag--rose"}`}
                      >
                        {v ? <Check size={9} /> : <X size={9} />}
                        {k}
                      </span>
                    ))}
                  </div>
                </div>
                <div
                  style={{
                    padding: 12,
                    background: "var(--slab-ink-3)",
                    border: "1px solid var(--slab-rule)",
                  }}
                >
                  <div className="slab-mono slab-mono--sm slab-mono--dim">
                    The Alpaca runner is using this class. To trade live, run:
                  </div>
                  <pre
                    className="slab-mono slab-mono--md"
                    style={{
                      color: "var(--slab-gold)",
                      marginTop: 8,
                      background: "var(--slab-ink-2)",
                      padding: "8px 12px",
                      border: "1px solid var(--slab-rule)",
                    }}
                  >
                    python -m app.services.alpaca_runner
                  </pre>
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* History */}
        <div className="slab-panel" style={{ maxWidth: 920, marginTop: 32 }}>
          <div className="slab-panel__head">
            <span className="slab-eyebrow slab-eyebrow--gold">
              <History size={11} style={{ verticalAlign: "middle", marginRight: 6 }} />
              Deployment history
            </span>
            <span className="slab-mono slab-mono--xs slab-mono--dim">
              {deployments.data?.length ?? 0} records
            </span>
          </div>
          <div style={{ maxHeight: 360, overflow: "auto" }}>
            {deployments.isLoading ? (
              <div style={{ padding: 16 }} className="slab-mono slab-mono--sm slab-mono--dim">Loading…</div>
            ) : !deployments.data || deployments.data.length === 0 ? (
              <div style={{ padding: 16 }} className="slab-mono slab-mono--sm slab-mono--faint">
                No deployments yet.
              </div>
            ) : (
              <table className="slab-table">
                <thead>
                  <tr>
                    <th>Class</th>
                    <th>Deployed at</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {deployments.data.map((d) => (
                    <tr key={d.deployment_id} className={d.is_active ? "slab-table__row--winner" : ""}>
                      <td style={{ color: d.is_active ? "var(--slab-gold)" : "var(--slab-paper-dim)" }}>
                        {d.class_name}
                      </td>
                      <td>{d.deployed_at?.slice(0, 19).replace("T", " ") ?? "—"}</td>
                      <td>
                        {d.is_active ? (
                          <span className="slab-tag slab-tag--gold">ACTIVE</span>
                        ) : (
                          <span className="slab-tag">rolled back</span>
                        )}
                      </td>
                      <td>
                        {d.is_active && (
                          <button
                            type="button"
                            onClick={() => rollback.mutate(d.deployment_id)}
                            disabled={rollback.isPending}
                            className="slab-btn slab-btn--xs"
                          >
                            <RotateCcw size={9} />
                            {rollback.isPending ? "rolling back…" : "rollback"}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* ChatPanel */}
        <ChatPanel
          sessionId={session.id}
          defaultModelId={session.model_id}
        />
      </div>

      {/* Confirm modal */}
      <AnimatePresence>
        {confirmOpen && (
          <ConfirmModal
            className={className.trim() || "<auto>"}
            onCancel={() => setConfirmOpen(false)}
            onConfirm={() => {
              setConfirmOpen(false);
              deployMut.mutate();
            }}
          />
        )}
      </AnimatePresence>
    </>
  );
}

function ConfirmModal({
  className,
  onCancel,
  onConfirm,
}: {
  className: string;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.7)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 50,
      }}
      onClick={onCancel}
    >
      <motion.div
        initial={{ y: 8, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 8, opacity: 0 }}
        className="slab-corner-marks slab-panel"
        style={{ position: "relative", width: "100%", maxWidth: 520 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="slab-panel__head">
          <span className="slab-eyebrow slab-eyebrow--gold">// Confirm deploy</span>
          <span className="slab-mono slab-mono--xs slab-mono--dim">paper only</span>
        </div>
        <div className="slab-panel__body" style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <p className="slab-prose">
            This will write a new Strategy class to{" "}
            <span className="slab-mono" style={{ color: "var(--slab-gold)" }}>
              backend/app/services/strategies/
            </span>{" "}
            and update <span className="slab-mono">alpaca_runner.py</span> to
            import it. Any active deployment will be deactivated.
          </p>
          <div
            style={{
              padding: 12,
              background: "var(--slab-ink-3)",
              border: "1px solid var(--slab-rule)",
            }}
          >
            <div className="slab-eyebrow">Target class</div>
            <div className="slab-mono slab-mono--md slab-mono--gold" style={{ marginTop: 4 }}>
              {className}
            </div>
          </div>
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}>
            <button type="button" onClick={onCancel} className="slab-btn">
              Cancel
            </button>
            <button
              type="button"
              onClick={onConfirm}
              className="slab-btn slab-btn--terminal"
            >
              <Rocket size={11} />
              Deploy
            </button>
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
