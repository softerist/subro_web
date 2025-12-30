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
    <div className="min-h-screen bg-background flex items-center justify-center p-4 page-enter">
      <div className="w-full max-w-md page-stagger">
        <Card className="bg-card/50 border-border backdrop-blur soft-hover">
          <CardHeader className="text-center">
            <CardTitle className="text-xl sm:text-2xl font-bold title-gradient">
              Login
            </CardTitle>
            <CardDescription className="text-muted-foreground">
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
