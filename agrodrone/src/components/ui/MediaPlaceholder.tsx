import { useId } from "react";
import { cn } from "@/lib/cn";

type Props = {
  /** Short label shown in the corner, e.g. "hero video". */
  label: string;
  tone?: "light" | "dark";
  className?: string;
};

/**
 * Tasteful stand-in for an image or video that is not ready yet. Renders a warm
 * neutral block with faint crop rows and a small corner label. Describe the
 * intended shot in a comment where the placeholder is used, so the asset can be
 * dropped in later without guessing.
 */
export function MediaPlaceholder({ label, tone = "light", className }: Props) {
  const id = useId();
  const patternId = `rows-${id.replace(/[^a-zA-Z0-9]/g, "")}`;
  const light = tone === "light";
  return (
    <div
      role="img"
      aria-label={`Placeholder for ${label}`}
      className={cn(
        "relative overflow-hidden rounded-2xl border",
        light ? "border-line bg-mist" : "border-paper/15 bg-paper/5",
        className,
      )}
    >
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <defs>
          <pattern id={patternId} width="100%" height="14" patternUnits="userSpaceOnUse">
            <line x1="0" y1="13.5" x2="100%" y2="13.5" stroke={light ? "#d9cfb8" : "#fafaf7"} strokeOpacity={light ? 0.7 : 0.12} strokeWidth="1" />
          </pattern>
        </defs>
        <rect width="100%" height="100%" fill={`url(#${patternId})`} />
      </svg>
      <span
        className={cn(
          "absolute bottom-3 left-3 rounded-full border px-2.5 py-1 text-[11px] font-medium tracking-wide",
          light ? "border-line bg-paper/80 text-ink-2" : "border-paper/20 bg-ink/60 text-paper/70",
        )}
      >
        Placeholder · {label}
      </span>
    </div>
  );
}
