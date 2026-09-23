import { cn } from "@/lib/cn";

/**
 * Top-down technical drawing of an Agras-class agricultural drone: four arms,
 * coaxial rotor pairs, centre tank, twin skids, and a spray boom with nozzles.
 * Inherits currentColor. Used as the fallback wherever aircraft photography is
 * not in place yet, and it reads as a deliberate blueprint rather than a gap.
 */
export function DroneDrawing({ className, spray = true }: { className?: string; spray?: boolean }) {
  const hubs: Array<[number, number]> = [
    [112, 96],
    [488, 96],
    [112, 304],
    [488, 304],
  ];
  const nozzles = [170, 222, 274, 326, 378, 430];
  return (
    <svg viewBox="0 0 600 400" className={cn("h-auto w-full", className)} aria-hidden="true" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round">
      {/* Span dimension */}
      <g strokeWidth="1" strokeOpacity="0.35">
        <line x1="48" y1="30" x2="552" y2="30" />
        <line x1="48" y1="24" x2="48" y2="36" />
        <line x1="552" y1="24" x2="552" y2="36" />
        <line x1="570" y1="32" x2="570" y2="368" />
        <line x1="564" y1="32" x2="576" y2="32" />
        <line x1="564" y1="368" x2="576" y2="368" />
      </g>
      {/* Arms */}
      <g strokeWidth="1.6">
        <line x1="268" y1="168" x2="112" y2="96" />
        <line x1="332" y1="168" x2="488" y2="96" />
        <line x1="268" y1="232" x2="112" y2="304" />
        <line x1="332" y1="232" x2="488" y2="304" />
      </g>
      {/* Rotors: disc outline, hub, two blades per stage */}
      {hubs.map(([cx, cy], i) => (
        <g key={i} transform={`translate(${cx} ${cy})`}>
          <circle r="64" strokeWidth="1" strokeOpacity="0.35" strokeDasharray="3 6" />
          <circle r="58" strokeWidth="1" strokeOpacity="0.2" />
          <g strokeWidth="3.2" strokeOpacity="0.9" transform={`rotate(${i % 2 === 0 ? 22 : -22})`}>
            <line x1="-56" y1="0" x2="56" y2="0" />
          </g>
          <g strokeWidth="2.2" strokeOpacity="0.45" transform={`rotate(${i % 2 === 0 ? 112 : -112})`}>
            <line x1="-50" y1="0" x2="50" y2="0" />
          </g>
          <circle r="7" strokeWidth="1.6" />
          <circle r="2" fill="currentColor" stroke="none" />
        </g>
      ))}
      {/* Skids */}
      <g strokeWidth="1.4" strokeOpacity="0.7">
        <line x1="236" y1="128" x2="236" y2="284" />
        <line x1="364" y1="128" x2="364" y2="284" />
        <line x1="236" y1="150" x2="268" y2="150" />
        <line x1="332" y1="150" x2="364" y2="150" />
        <line x1="236" y1="250" x2="268" y2="250" />
        <line x1="332" y1="250" x2="364" y2="250" />
      </g>
      {/* Body and tank */}
      <rect x="268" y="150" width="64" height="100" rx="12" strokeWidth="1.8" />
      <circle cx="300" cy="200" r="27" strokeWidth="1.6" />
      <circle cx="300" cy="200" r="15" strokeWidth="1" strokeOpacity="0.5" />
      <line x1="300" y1="150" x2="300" y2="132" strokeWidth="1.4" />
      <circle cx="300" cy="126" r="6" strokeWidth="1.4" />
      {/* Spray boom and nozzles */}
      <g strokeWidth="1.4">
        <line x1="150" y1="272" x2="450" y2="272" />
        <line x1="300" y1="250" x2="300" y2="272" />
        {nozzles.map((x) => (
          <g key={x}>
            <line x1={x} y1="266" x2={x} y2="282" />
            <circle cx={x} cy="284" r="2.2" fill="currentColor" stroke="none" />
          </g>
        ))}
      </g>
      {spray && (
        <g className="drone-spray" strokeWidth="1" strokeOpacity="0.45" strokeDasharray="1 5">
          {nozzles.map((x) => (
            <g key={x}>
              <line x1={x} y1="290" x2={x - 14} y2="340" />
              <line x1={x} y1="290" x2={x} y2="346" />
              <line x1={x} y1="290" x2={x + 14} y2="340" />
            </g>
          ))}
        </g>
      )}
    </svg>
  );
}
