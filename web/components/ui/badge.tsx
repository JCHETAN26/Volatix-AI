import * as React from "react";

import { cn } from "@/lib/cn";

type Tone = "default" | "green" | "red" | "amber" | "blue";

const toneStyles: Record<Tone, string> = {
  default: "bg-white/10 text-white/80 ring-white/10",
  green: "bg-accent-green/15 text-accent-green ring-accent-green/30",
  red: "bg-accent-red/15 text-accent-red ring-accent-red/30",
  amber: "bg-accent-amber/15 text-accent-amber ring-accent-amber/30",
  blue: "bg-accent-blue/15 text-accent-blue ring-accent-blue/30",
};

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  tone?: Tone;
}

export function Badge({ tone = "default", className, ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium",
        "ring-1 ring-inset",
        toneStyles[tone],
        className,
      )}
      {...props}
    />
  );
}
