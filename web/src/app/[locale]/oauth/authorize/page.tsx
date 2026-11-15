import { Suspense } from "react";

import { AuthLayout } from "@/components/auth-layout";
import { OAuthConsent } from "@/components/oauth-consent";

// Consent page for OAuth clients such as claude.ai connectors. The API's
// /oauth/authorize checks the request and sends the browser here.
export default function OAuthAuthorizePage() {
  return (
    <AuthLayout>
      {/* OAuthConsent reads the query string, which needs a Suspense boundary in a static export. */}
      <Suspense>
        <OAuthConsent />
      </Suspense>
    </AuthLayout>
  );
}
