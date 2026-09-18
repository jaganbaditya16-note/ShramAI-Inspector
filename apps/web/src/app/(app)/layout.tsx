"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { AppShell } from "@/components/app/shell";
import { useSession } from "@/hooks/use-session";
import { Skeleton } from "@/components/ui/feedback";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { isLoading, needsLogin } = useSession();
  const router = useRouter();

  useEffect(() => {
    if (needsLogin) {
      router.replace("/login");
    }
  }, [needsLogin, router]);

  if (isLoading) {
    return (
      <div className="shell">
        <div style={{ padding: 28, width: "100%" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 720 }}>
            <Skeleton style={{ width: "30%", height: 26 }} />
            <Skeleton style={{ width: "100%", height: 120 }} />
            <Skeleton style={{ width: "100%", height: 200 }} />
          </div>
        </div>
      </div>
    );
  }

  if (needsLogin) {
    return null;
  }

  return <AppShell>{children}</AppShell>;
}
