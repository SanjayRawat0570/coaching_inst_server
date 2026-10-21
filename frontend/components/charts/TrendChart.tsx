import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";

/** One line over time (teacher monthly scores, admin weekly engagement).
 * Loaded with next/dynamic, so Recharts only downloads where a chart is drawn. */
export default function TrendChart({ data, xKey, yKey, label, percent = false }: {
  data: any[]; xKey: string; yKey: string; label: string; percent?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <LineChart data={data} margin={{ left: -10, right: 10, top: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(148,163,184,0.15)" />
        <XAxis dataKey={xKey} tick={{ fontSize: 12, fill: "#94a3b8" }} />
        <YAxis domain={percent ? [0, 100] : undefined} tick={{ fontSize: 12, fill: "#94a3b8" }} />
        <Tooltip
          contentStyle={{ background: "#0b1120", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#e2e8f0" }}
          formatter={(v) => [percent ? `${v}%` : v, label]}
        />
        <Line type="monotone" dataKey={yKey} stroke="#4f46e5" strokeWidth={2.5} dot={{ r: 4 }} activeDot={{ r: 6 }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
