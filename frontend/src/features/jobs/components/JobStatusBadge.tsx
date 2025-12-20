import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

interface JobStatusBadgeProps {
  status: string;
  className?: string;
}

export function JobStatusBadge({ status, className }: JobStatusBadgeProps) {
  const getVariant = (status: string) => {
    switch (status) {
      case "SUCCEEDED":
        return "bg-green-500 hover:bg-green-600 border-transparent text-white";
      case "FAILED":
        return "bg-red-500 hover:bg-red-600 border-transparent text-white";
      case "RUNNING":
        return "bg-blue-500 hover:bg-blue-600 border-transparent text-white animate-pulse";
      case "PENDING":
        return "bg-yellow-500 hover:bg-yellow-600 border-transparent text-white";
      case "CANCELLED":
        return "bg-gray-500 hover:bg-gray-600 border-transparent text-white";
      default:
        return "bg-gray-500 hover:bg-gray-600 border-transparent text-white";
    }
  };

  return (
    <Badge className={cn(getVariant(status), className)} variant="default">
      {status}
    </Badge>
  );
}
