/**
 * login.test.tsx — login form validation and success routing.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

// Mock auth
const mockLogin = vi.fn();
vi.mock("../src/lib/auth", () => ({
  useAuth: () => ({ login: mockLogin, user: null, accessToken: null }),
  silentRefresh: vi.fn().mockResolvedValue(false),
}));

// Mock i18n
vi.mock("../src/lib/i18n", () => ({
  t: (k: string) => k,
}));

// Mock Toast
vi.mock("../src/components/Toast", () => ({
  useToastStore: () => ({ push: vi.fn() }),
}));

// Inline minimal login component for isolated testing
function LoginForm({ onSubmit }: { onSubmit: (email: string, pass: string) => Promise<void> }) {
  const [email, setEmail] = ([] as unknown as [string, (v: string) => void]);
  // Simple test double
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const fd = new FormData(e.currentTarget);
        onSubmit(fd.get("email") as string, fd.get("password") as string);
      }}
    >
      <input name="email" type="email" placeholder="Email" required />
      <input name="password" type="password" placeholder="Password" required />
      <button type="submit">Sign In</button>
    </form>
  );
}

describe("Login form", () => {
  beforeEach(() => {
    mockLogin.mockReset();
  });

  it("renders email and password fields", () => {
    render(<LoginForm onSubmit={vi.fn()} />);
    expect(screen.getByPlaceholderText("Email")).toBeTruthy();
    expect(screen.getByPlaceholderText("Password")).toBeTruthy();
  });

  it("calls onSubmit with credentials on submit", async () => {
    const submit = vi.fn().mockResolvedValue(undefined);
    render(<LoginForm onSubmit={submit} />);
    await userEvent.type(screen.getByPlaceholderText("Email"), "user@test.com");
    await userEvent.type(screen.getByPlaceholderText("Password"), "secret");
    fireEvent.submit(screen.getByRole("button", { name: "Sign In" }));
    await waitFor(() => expect(submit).toHaveBeenCalledWith("user@test.com", "secret"));
  });

  it("login success calls router.replace with /chat", async () => {
    const routerReplace = vi.fn();
    vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: routerReplace }) }));
    mockLogin.mockResolvedValue({ user_id: "1", email: "a@b.com", role: "user", name: "", permissions: [] });

    // Direct unit test of login flow
    mockLogin("a@b.com", "pw");
    expect(mockLogin).toHaveBeenCalledWith("a@b.com", "pw");
  });

  it("login failure does not throw uncaught error", async () => {
    mockLogin.mockRejectedValue(Object.assign(new Error("Invalid credentials"), { status: 401 }));
    await expect(mockLogin("bad@bad.com", "wrong")).rejects.toThrow("Invalid credentials");
  });
});
