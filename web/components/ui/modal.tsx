"use client";

import * as React from "react";

import { cn } from "@/lib/cn";

interface ModalProps {
  open: boolean;
  onClose: () => void;
  className?: string;
  children: React.ReactNode;
  /** Accessible name. */
  label?: string;
}

/**
 * Zero-dep modal built on the native <dialog> element. Handles:
 *   - backdrop click → close
 *   - ESC → close (native)
 *   - body scroll lock while open
 *   - showModal()/close() lifecycle synced to the `open` prop
 *
 * Caller owns the open state. Use for cases where Radix Dialog would
 * be overkill — we don't need focus traps or animation primitives here.
 */
export function Modal({ open, onClose, children, className, label }: ModalProps) {
  const ref = React.useRef<HTMLDialogElement | null>(null);

  React.useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (open && !node.open) {
      node.showModal();
    } else if (!open && node.open) {
      node.close();
    }
  }, [open]);

  React.useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  const handleNativeClose = React.useCallback(() => {
    onClose();
  }, [onClose]);

  const handleBackdropClick = React.useCallback(
    (e: React.MouseEvent<HTMLDialogElement>) => {
      // The dialog *element* receives clicks on the backdrop; clicks on
      // children bubble through but with a different `target`.
      if (e.target === ref.current) onClose();
    },
    [onClose],
  );

  return (
    <dialog
      ref={ref}
      onClose={handleNativeClose}
      onClick={handleBackdropClick}
      aria-label={label}
      className={cn(
        "bg-transparent text-white p-0 m-auto",
        "backdrop:bg-black/70 backdrop:backdrop-blur-sm",
        "outline-none",
      )}
    >
      <div
        className={cn(
          "rounded-lg border border-white/10 bg-bg-panel/95 shadow-2xl",
          "w-[min(900px,calc(100vw-2rem))]",
          "max-h-[calc(100vh-3rem)] overflow-hidden flex flex-col",
          className,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </dialog>
  );
}
