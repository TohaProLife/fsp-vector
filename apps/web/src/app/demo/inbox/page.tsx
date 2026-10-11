import { Suspense } from "react";
import { DemoInbox } from "@/components/auth";
export default function Page() {
  return (
    <Suspense>
      <DemoInbox />
    </Suspense>
  );
}
