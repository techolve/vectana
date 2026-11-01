import { Suspense } from "react";

import { AuthLayout } from "@/components/auth-layout";
import { LoginForm } from "@/components/login-form";

export default function LoginPage() {
  return (
    <AuthLayout>
      {/* LoginForm reads ?sso_error, which needs a Suspense boundary in a static export. */}
      <Suspense>
        <LoginForm />
      </Suspense>
    </AuthLayout>
  );
}
