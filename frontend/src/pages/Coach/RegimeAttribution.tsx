import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';

const COLORS = ['#10b981', '#f43f5e', '#f59e0b', '#3b82f6'];

export function RegimeAttribution({
  data,
}: {
  data: Record<string, { n: number; pnl: number; pnl_pct: number }>;
}) {
  const rows = Object.entries(data).map(([regime, v]) => ({ regime, ...v }));
  if (rows.length === 0) {
    return <div className="text-zinc-500 text-sm">No closed trades in this period.</div>;
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={rows} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis dataKey="regime" stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} />
          <Bar dataKey="pnl">
            {rows.map((_, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
