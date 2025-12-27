import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { LoginForm } from "@/features/auth/components/LoginForm";

export default function LoginPage() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 flex items-center justify-center p-4 page-enter">
      <div className="w-full max-w-md page-stagger">
        <Card className="bg-slate-800/50 border-slate-700 backdrop-blur soft-hover">
          <CardHeader className="text-center">
            <CardTitle className="text-2xl text-white">Login</CardTitle>
            <CardDescription className="text-slate-400">
              Enter your email below to login to your account.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <LoginForm />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
