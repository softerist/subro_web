import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAuthStore } from "@/store/authStore";
import { authApi } from "@/features/auth/api/auth";
import { cn } from "@/lib/utils";

export function LoginForm({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);

  const mutation = useMutation({
    mutationFn: authApi.login,
    onSuccess: async (data) => {
      // data contains access_token and token_type
      const accessToken = data.access_token;

      // Fetch user details immediately to populate store
      // We manually set token first so getMe works
      useAuthStore.getState().setAccessToken(accessToken);

      try {
        const user = await authApi.getMe();
        login(accessToken, {
          id: user.id,
          email: user.email,
          role: user.role ?? "user",
          is_superuser: user.is_superuser ?? false,
        });
        navigate("/dashboard");
      } catch (err) {
        setError("Failed to fetch user profile.");
      }
    },
    onError: (_err: Error) => {
      setError("Invalid email or password.");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    mutation.mutate({ username: email, password });
  };

  return (
    <div className={cn("grid gap-6", className)} {...props}>
      <form onSubmit={handleSubmit} action="/login" method="post">
        <div className={cn("grid gap-4")}>
          <div className="grid gap-2">
            <Label htmlFor="email" className="text-slate-300">
              Email
            </Label>
            <Input
              id="email"
              name="email"
              placeholder="name@example.com"
              type="email"
              autoCapitalize="none"
              autoComplete="email"
              autoCorrect="off"
              disabled={mutation.isPending}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
            />
          </div>
          <div className="grid gap-2">
            <Label htmlFor="password" className="text-slate-300">
              Password
            </Label>
            <Input
              id="password"
              name="password"
              placeholder="Password"
              type="password"
              autoComplete="current-password"
              disabled={mutation.isPending}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>
          {error && <p className="text-sm text-red-400">{error}</p>}
          <Button disabled={mutation.isPending}>
            {mutation.isPending && (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            )}
            Sign In
          </Button>
        </div>
      </form>
    </div>
  );
}
