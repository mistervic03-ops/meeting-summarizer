const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";

interface AuthStatusResponse {
  authenticated: boolean;
}

export async function getAuthStatus(): Promise<boolean> {
  const response = await fetch(`${API_BASE_URL}/auth/me`, {
    credentials: "include"
  });
  if (!response.ok) {
    return false;
  }

  const body = (await response.json()) as AuthStatusResponse;
  return body.authenticated;
}

export async function loginWithPassword(password: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json"
    },
    body: JSON.stringify({ password })
  });

  if (!response.ok) {
    throw new Error("비밀번호가 틀렸습니다.");
  }
}

export async function logoutGateway(): Promise<void> {
  await fetch(`${API_BASE_URL}/auth/logout`, {
    method: "POST",
    credentials: "include"
  });
}
