import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "../../components/ui/Button";
import { strategyLabApi, type StrategySession } from "../../lib/strategyLab";

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
    <div className="space-y-6 p-6">
      <header>
        <h2 className="text-xl font-semibold text-zinc-100">5. Deploy to Alpaca</h2>
        <p className="mt-1 text-sm text-zinc-400">
          Promote the winning experiment to a live Strategy class on Alpaca paper.
        </p>
      </header>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="mb-2 text-sm font-semibold text-zinc-200">Selected experiment</h3>
        <div className="font-mono text-xs text-zinc-400">
          {experimentId.slice(0, 8)}…
        </div>
        <div className="mt-3">
          <label className="mb-1 block text-sm text-zinc-300">
            Class name (optional — auto-generated from session name + date)
          </label>
          <input
            type="text"
            value={className}
            onChange={(e) => setClassName(e.target.value)}
            placeholder="e.g. GoldenCrossV20240615"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100 placeholder-zinc-500 focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div className="mt-4">
          <Button onClick={() => setConfirmOpen(true)} disabled={deployMut.isPending}>
            {deployMut.isPending ? "Deploying…" : "🚀 Deploy to Alpaca"}
          </Button>
        </div>
        {deployMut.isError && (
          <div className="mt-3 text-sm text-red-400">
            {String((deployMut.error as Error)?.message ?? "Deploy failed")}
          </div>
        )}
        {deployMut.isSuccess && deployMut.data && (
          <div className="mt-3 rounded-md border border-emerald-800 bg-emerald-950/30 p-3 text-sm">
            <div className="font-semibold text-emerald-300">
              ✓ Deployed {deployMut.data.class_name}
            </div>
            <div className="mt-1 text-xs text-zinc-400">
              <div>File: <span className="font-mono">{deployMut.data.class_file_path}</span></div>
              <div className="mt-1">
                Verification:{" "}
                {Object.entries(deployMut.data.verification ?? {}).map(([k, v]) => (
                  <span
                    key={k}
                    className={`mr-2 rounded px-1.5 py-0.5 text-xs ${v ? "bg-emerald-900/50 text-emerald-300" : "bg-red-900/50 text-red-300"}`}
                  >
                    {k}: {v ? "✓" : "✗"}
                  </span>
                ))}
              </div>
              <div className="mt-2 text-xs text-zinc-500">
                The Alpaca runner is now using this class. To trade live, run{" "}
                <code className="rounded bg-zinc-800 px-1 py-0.5">
                  python -m app.services.alpaca_runner
                </code>{" "}
                on your paper account.
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="rounded-lg border border-zinc-800 bg-zinc-900/30 p-4">
        <h3 className="mb-3 text-sm font-semibold text-zinc-200">Deployment history</h3>
        {deployments.isLoading ? (
          <div className="text-sm text-zinc-400">Loading…</div>
        ) : !deployments.data || deployments.data.length === 0 ? (
          <div className="text-sm text-zinc-500">No deployments yet.</div>
        ) : (
          <table className="w-full text-sm">
            <thead className="text-zinc-400">
              <tr>
                <th className="px-2 py-1 text-left">Class</th>
                <th className="px-2 py-1 text-left">Deployed</th>
                <th className="px-2 py-1 text-left">Status</th>
                <th className="px-2 py-1 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {deployments.data.map((d) => (
                <tr key={d.deployment_id} className="border-t border-zinc-800">
                  <td className="px-2 py-1 font-mono text-zinc-200">{d.class_name}</td>
                  <td className="px-2 py-1 text-xs text-zinc-400">
                    {d.deployed_at?.slice(0, 19).replace("T", " ") ?? "—"}
                  </td>
                  <td className="px-2 py-1">
                    {d.is_active ? (
                      <span className="rounded bg-emerald-900/50 px-2 py-0.5 text-xs text-emerald-300">active</span>
                    ) : (
                      <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs text-zinc-500">rolled back</span>
                    )}
                  </td>
                  <td className="px-2 py-1 text-right">
                    {d.is_active && (
                      <button
                        onClick={() => rollback.mutate(d.deployment_id)}
                        disabled={rollback.isPending}
                        className="text-xs text-amber-400 hover:text-amber-300 disabled:opacity-50"
                      >
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

      {confirmOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => setConfirmOpen(false)}
        >
          <div
            className="w-full max-w-md rounded-lg border border-zinc-700 bg-zinc-900 p-6 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="text-lg font-semibold text-zinc-100">Confirm deploy</h3>
            <p className="mt-2 text-sm text-zinc-400">
              This will write a new Strategy class file to{" "}
              <code className="rounded bg-zinc-800 px-1 py-0.5 text-xs">
                backend/app/services/strategies/
              </code>{" "}
              and update <code className="rounded bg-zinc-800 px-1 py-0.5 text-xs">alpaca_runner.py</code>{" "}
              to import it. Any active deployment will be deactivated.
            </p>
            <p className="mt-3 text-sm text-zinc-400">Target: 📄 Paper account only.</p>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setConfirmOpen(false)}
                className="rounded-md border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-700"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  setConfirmOpen(false);
                  deployMut.mutate();
                }}
                className="rounded-md bg-emerald-500 px-3 py-1.5 text-sm font-semibold text-black hover:bg-emerald-400"
              >
                Yes, deploy
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
