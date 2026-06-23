import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium",
  {
    variants: {
      variant: {
        default: "border-white/10 bg-secondary text-secondary-foreground",
        outline: "border-border bg-transparent text-foreground/80",
        success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300",
        warn: "border-amber-500/30 bg-amber-500/10 text-amber-300",
        danger: "border-rose-500/30 bg-rose-500/10 text-rose-300",
        info: "border-sky-500/30 bg-sky-500/10 text-sky-300",
        brand: "border-brand-500/30 bg-brand-500/10 text-brand-300",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
