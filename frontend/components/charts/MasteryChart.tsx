import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from "recharts";

function scoreColor(score) {
  if (score >= 0.8) return "#16a34a"; // strong
  if (score >= 0.5) return "#f59e0b"; // medium
  return "#dc2626"; // weak
}

/** Per-concept mastery bars. Loaded with next/dynamic, so Recharts (~100 kB gzip)
 * is only downloaded by pages that draw a chart, after the page itself shows. */
export default function MasteryChart({ data }: { data: { name: string; score: number; raw: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={Math.max(220, data.length * 34)}>
      <BarChart data={data} layout="vertical" margin={{ left: 40 }}>
        <XAxis type="number" domain={[0, 100]} hide />
        <YAxis type="category" dataKey="name" width={140} tick={{ fontSize: 12, fill: "#94a3b8" }} />
        <Tooltip
          contentStyle={{ background: "#0b1120", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 12, color: "#e2e8f0" }}
          cursor={{ fill: "rgba(255,255,255,0.04)" }}
        />
        <Bar dataKey="score" radius={[0, 6, 6, 0]}>
          {data.map((entry, i) => (
            <Cell key={i} fill={scoreColor(entry.raw)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
