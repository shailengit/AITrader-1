import { coachApi, type Trade } from '../../lib/coach';

export function TradeTable({
  rows,
  onChanged,
}: {
  rows: Trade[];
  onChanged: () => void;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-xs uppercase text-zinc-500">
          <tr>
            <th className="px-3 py-2 text-left">Ticker</th>
            <th className="px-3 py-2 text-left">Side</th>
            <th className="px-3 py-2 text-right">Qty</th>
            <th className="px-3 py-2 text-right">Entry</th>
            <th className="px-3 py-2 text-right">Exit</th>
            <th className="px-3 py-2 text-right">P&L</th>
            <th className="px-3 py-2 text-left">Opened</th>
            <th className="px-3 py-2 text-left">Closed</th>
            <th className="px-3 py-2 text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={9} className="px-3 py-6 text-center text-zinc-500">
                No trades yet. Add one above.
              </td>
            </tr>
          ) : (
            rows.map((t) => (
              <tr key={t.id} className="border-t border-zinc-800">
                <td className="px-3 py-2 font-mono">{t.ticker}</td>
                <td className="px-3 py-2">{t.side}</td>
                <td className="px-3 py-2 text-right">{t.qty}</td>
                <td className="px-3 py-2 text-right">{t.entry_px.toFixed(2)}</td>
                <td className="px-3 py-2 text-right">
                  {t.exit_px != null ? t.exit_px.toFixed(2) : '—'}
                </td>
                <td
                  className={`px-3 py-2 text-right ${
                    (t.pnl ?? 0) >= 0 ? 'text-emerald-500' : 'text-rose-500'
                  }`}
                >
                  {t.pnl != null ? t.pnl.toFixed(2) : '—'}
                </td>
                <td className="px-3 py-2">{t.entry_at?.slice(0, 10)}</td>
                <td className="px-3 py-2">{t.exit_at?.slice(0, 10) ?? 'open'}</td>
                <td className="px-3 py-2 text-right">
                  {t.exit_at == null && (
                    <button
                      onClick={async () => {
                        await coachApi.closeTrade(t.id, {});
                        onChanged();
                      }}
                      className="rounded-md border border-emerald-700 px-2 py-1 text-xs text-emerald-400 hover:bg-emerald-900/30"
                    >
                      Close
                    </button>
                  )}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
