import * as React from "react";

import { cn } from "@/lib/cn";

interface EmptyStateProps {
  title: string;
  description?: React.ReactNode;
  className?: string;
}

export function EmptyState({ title, description, className }: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-1 py-10 text-center",
        "text-white/40 text-sm",
        className,
      )}
    >
      <p className="font-medium text-white/60">{title}</p>
      {description ? <p className="max-w-md">{description}</p> : null}
    </div>
  );
}
