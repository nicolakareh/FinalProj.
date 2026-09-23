import type { ElementType, ReactNode } from "react";
import { cn } from "@/lib/cn";

type Props = {
  as?: ElementType;
  className?: string;
  children: ReactNode;
};

export function Container({ as: Tag = "div", className, children }: Props) {
  return <Tag className={cn("mx-auto w-full max-w-[1200px] px-5 sm:px-8", className)}>{children}</Tag>;
}
