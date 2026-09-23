import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ArrowRight } from "./Icons";

type Variant = "primary" | "inverse" | "ghost" | "ghost-inverse";
type Size = "sm" | "md" | "lg";

type Common = {
  variant?: Variant;
  size?: Size;
  arrow?: boolean;
  className?: string;
  children: ReactNode;
};

type LinkProps = Common & { href: string; onClick?: () => void };
type ButtonProps = Common & {
  href?: undefined;
  type?: ButtonHTMLAttributes<HTMLButtonElement>["type"];
  onClick?: () => void;
  disabled?: boolean;
};

const variants: Record<Variant, string> = {
  primary: "bg-ink text-paper hover:bg-field",
  inverse: "bg-paper text-ink hover:bg-white",
  ghost: "border border-ink/20 text-ink hover:border-ink hover:bg-ink/5",
  "ghost-inverse": "border border-paper/30 text-paper hover:border-paper hover:bg-paper/10",
};

const sizes: Record<Size, string> = {
  sm: "h-9 px-4 text-sm",
  md: "h-11 px-5 text-[15px]",
  lg: "h-12 px-6 text-base",
};

const baseClass =
  "group inline-flex items-center justify-center gap-2 rounded-full font-medium whitespace-nowrap select-none transition-[background-color,color,border-color,transform] duration-200 ease-out active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-field disabled:pointer-events-none disabled:opacity-50";

function Arrow() {
  return <ArrowRight className="transition-transform duration-200 ease-out group-hover:translate-x-0.5" />;
}

export function Button(props: LinkProps | ButtonProps) {
  const { variant = "primary", size = "md", arrow = false, className, children } = props;
  const classes = cn(baseClass, variants[variant], sizes[size], className);

  if (props.href !== undefined) {
    return (
      <a href={props.href} onClick={props.onClick} className={classes}>
        {children}
        {arrow && <Arrow />}
      </a>
    );
  }
  return (
    <button type={props.type ?? "button"} onClick={props.onClick} disabled={props.disabled} className={classes}>
      {children}
      {arrow && <Arrow />}
    </button>
  );
}
