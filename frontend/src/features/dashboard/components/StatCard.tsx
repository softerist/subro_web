import { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

type StatVariant = "blue" | "green" | "purple" | "orange" | "pink";

interface StatCardProps {
  icon: LucideIcon;
  value: string | number;
  label: string;
  variant?: StatVariant;
  trend?: {
    value: number;
    isPositive: boolean;
  };
  className?: string;
}

export function StatCard({
  icon: Icon,
  value,
  label,
  variant = "blue",
  trend,
  className,
}: StatCardProps) {
  return (
    <div className={cn("stat-card", className)}>
      <div className={cn("stat-card-icon", variant)}>
        <Icon className="h-4 w-4 text-white" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2">
          <span className="stat-card-value">{value}</span>
          {trend && (
            <span
              className={cn(
                "text-xs font-medium",
                trend.isPositive ? "text-green-500" : "text-red-500",
              )}
            >
              {trend.isPositive ? "+" : ""}
              {trend.value}%
            </span>
          )}
        </div>
        <p className="stat-card-label">{label}</p>
      </div>
    </div>
  );
}
