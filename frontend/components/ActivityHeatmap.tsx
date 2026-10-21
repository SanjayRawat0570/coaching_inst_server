// F6 — a 24-hour activity heatmap. Renders 24 hour-of-day cells (IST) whose
// colour intensity scales with activity volume. `hours` is an array of 24 ints.
import Icon from "./Icon";

function hourLabel(h) {
  const period = h < 12 ? "am" : "pm";
  const hr = h % 12 === 0 ? 12 : h % 12;
  return `${hr}${period}`;
}

export default function ActivityHeatmap({ hours = [], total = 0, days = 14 }) {
  const cells = hours.length === 24 ? hours : new Array(24).fill(0);
  const max = Math.max(1, ...cells);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 mb-3">
        <h2 className="h-section flex items-center gap-2">
          <Icon name="clock" size={16} /> When students are active (24h)
        </h2>
        <span className="muted text-xs">last {days} days · IST</span>
      </div>

      {total === 0 ? (
        <p className="muted text-sm py-4">
          No activity logged yet. Once students log in or practise, their busiest
          hours will light up here.
        </p>
      ) : (
        <>
          <div className="flex gap-[3px]">
            {cells.map((count, h) => {
              const intensity = count / max; // 0..1
              // Faint track for empty hours; indigo that deepens with volume.
              const bg = count === 0
                ? "rgba(148,163,184,0.12)"
                : `rgba(99,102,241,${0.18 + intensity * 0.82})`;
              return (
                <div key={h} className="flex-1 group relative">
                  <div
                    className="h-9 rounded-[3px] transition-transform group-hover:scale-y-110"
                    style={{ backgroundColor: bg }}
                    title={`${hourLabel(h)}–${hourLabel((h + 1) % 24)}: ${count} action${count === 1 ? "" : "s"}`}
                  />
                </div>
              );
            })}
          </div>
          {/* hour axis ticks */}
          <div className="flex justify-between mt-1.5 text-[10px] muted tabular-nums">
            <span>12am</span><span>6am</span><span>12pm</span><span>6pm</span><span>11pm</span>
          </div>
          <p className="muted text-xs mt-3">{total} actions across the window.</p>
        </>
      )}
    </div>
  );
}
