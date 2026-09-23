import { cn } from "@/lib/cn";
import { Eyebrow } from "./Eyebrow";
import { Reveal } from "./Reveal";

type Props = {
  eyebrow: string;
  title: string;
  lead?: string;
  align?: "left" | "center";
  tone?: "light" | "dark";
  className?: string;
};

export function SectionHeader({ eyebrow, title, lead, align = "left", tone = "light", className }: Props) {
  const centered = align === "center";
  return (
    <div className={cn("max-w-[52rem]", centered && "mx-auto text-center", className)}>
      <Reveal y={12}>
        <Eyebrow tone={tone} className={cn(centered && "justify-center")}>
          {eyebrow}
        </Eyebrow>
      </Reveal>
      <Reveal delay={0.08}>
        <h2 className={cn("type-h2 mt-5", centered ? "mx-auto max-w-[20ch]" : "max-w-[20ch]")}>{title}</h2>
      </Reveal>
      {lead && (
        <Reveal delay={0.16}>
          <p className={cn("type-lead mt-5", tone === "light" ? "text-ink-2" : "text-paper/70", centered ? "mx-auto max-w-[46ch]" : "max-w-[46ch]")}>
            {lead}
          </p>
        </Reveal>
      )}
    </div>
  );
}
