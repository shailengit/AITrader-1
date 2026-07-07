import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export function EquityCurve({ data }: { data: { date: string; equity: number }[] }) {
  if (!data || data.length === 0) {
    return <div className="text-zinc-500 text-sm">No closed trades in this period.</div>;
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis dataKey="date" stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} />
          <Line type="monotone" dataKey="equity" stroke="#10b981" dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
