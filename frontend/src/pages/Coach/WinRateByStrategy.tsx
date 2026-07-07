import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';

export function WinRateByStrategy({
  data,
}: {
  data: { name: string; n: number; win_rate: number }[];
}) {
  if (!data || data.length === 0) {
    return <div className="text-zinc-500 text-sm">No strategies with closed trades in this period.</div>;
  }
  return (
    <div className="h-72 w-full">
      <ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ top: 8, right: 16, bottom: 8, left: 64 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#3f3f46" />
          <XAxis type="number" domain={[0, 1]} stroke="#a1a1aa" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="name" stroke="#a1a1aa" tick={{ fontSize: 11 }} width={120} />
          <Tooltip contentStyle={{ background: '#18181b', border: '1px solid #3f3f46' }} />
          <Bar dataKey="win_rate" fill="#3b82f6" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
