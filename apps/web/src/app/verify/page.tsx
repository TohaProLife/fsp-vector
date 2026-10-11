import { Suspense } from "react";
import { Verification } from "@/components/auth";
export default function Page() {
  return (
    <Suspense>
      <Verification />
    </Suspense>
  );
}
