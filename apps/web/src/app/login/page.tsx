import { Suspense } from "react";
import { AuthPage } from "@/components/auth";
export default function Page() {
  return (
    <Suspense>
      <AuthPage />
    </Suspense>
  );
}
