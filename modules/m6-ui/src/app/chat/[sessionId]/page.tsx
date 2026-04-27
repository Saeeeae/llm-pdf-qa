"use client";
/**
 * Existing chat session page.
 * Loads session history from /api/v1/chat/sessions/{id} then delegates to chat UI.
 * Currently renders a stub — session history hydration is handled by M5 gateway.
 */
import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../../lib/auth";

export default function SessionPage({ params }: { params: { sessionId: string } }) {
  const router = useRouter();
  const { user } = useAuth();

  useEffect(() => {
    if (!user) {
      router.replace("/login");
      return;
    }
    // Redirect to /chat with the session pre-selected via query param.
    // The chat page loads session history from M5 via /api/v1/chat/sessions/{id}.
    router.replace(`/chat?session=${params.sessionId}`);
  }, [user, router, params.sessionId]);

  return null;
}
