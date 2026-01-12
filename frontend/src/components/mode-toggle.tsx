import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";

export function ModeToggle() {
  const { resolvedTheme, setTheme } = useTheme();

  const isDark = resolvedTheme === "dark";

  const toggleTheme = (checked: boolean) => {
    setTheme(checked ? "dark" : "light");
  };

  return (
    <div className="flex items-center space-x-3">
      <Sun className="h-4 w-4 text-muted-foreground" />
      <Switch
        id="theme-mode"
        checked={isDark}
        onCheckedChange={toggleTheme}
        className="data-[state=checked]:bg-primary"
        aria-label="Toggle theme"
      />
      <Moon className="h-4 w-4 text-muted-foreground" />
      <Label htmlFor="theme-mode" className="sr-only">
        Toggle theme
      </Label>
    </div>
  );
}
