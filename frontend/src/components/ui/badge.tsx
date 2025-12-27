import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-white/60 focus:ring-offset-2 focus:ring-offset-slate-900",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-slate-700 text-slate-100 hover:bg-slate-600",
        secondary:
          "border-transparent bg-slate-800 text-slate-100 hover:bg-slate-700",
        destructive:
          "border-transparent bg-red-500/20 text-red-300 hover:bg-red-500/30",
        outline: "border-slate-600 text-slate-200",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  );
}

export { Badge, badgeVariants };
