import { site } from "@/content/site";
import { cn } from "@/lib/cn";

/** Quad-rotor glyph plus the name. Inherits currentColor so it works on light or dark. */
export function Wordmark({ className }: { className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-2 font-semibold tracking-[-0.02em]", className)}>
      <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true" className="shrink-0">
        <circle cx="5" cy="5" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="17" cy="5" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="5" cy="17" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <circle cx="17" cy="17" r="3.2" fill="none" stroke="currentColor" strokeWidth="1.6" />
        <path d="M7.4 7.4 14.6 14.6M14.6 7.4 7.4 14.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="11" cy="11" r="2.1" fill="currentColor" />
      </svg>
      <span className="text-[17px]">{site.name}</span>
    </span>
  );
}
