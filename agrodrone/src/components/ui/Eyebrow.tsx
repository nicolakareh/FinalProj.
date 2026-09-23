import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Eyebrow({ children, className, tone = "light" }: { children: ReactNode; className?: string; tone?: "light" | "dark" }) {
  return (
    <p className={cn("type-eyebrow inline-flex items-center gap-2.5", tone === "light" ? "text-field" : "text-paper/70", className)}>
      <span className={cn("h-px w-5", tone === "light" ? "bg-field" : "bg-paper/50")} aria-hidden="true" />
      {children}
    </p>
  );
}
