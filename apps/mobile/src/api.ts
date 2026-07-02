import { Platform } from "react-native";
import type {
  ConnectionInfo,
  Platform as SnsPlatform,
  PostInput,
  UniversalPost,
  ValidationIssue,
} from "@crosspost/shared";

function defaultBaseUrl(): string {
  // Android emulators reach the host machine via 10.0.2.2.
  if (Platform.OS === "android") return "http://10.0.2.2:4000";
  return "http://localhost:4000";
}

const BASE_URL = process.env.EXPO_PUBLIC_API_URL || defaultBaseUrl();

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.error) message = body.error;
    } catch {
      // non-JSON error body
    }
    throw new Error(message);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listPosts: () =>
    request<{ posts: UniversalPost[] }>("/api/posts").then((r) => r.posts),

  createPost: (input: PostInput) =>
    request<{ post: UniversalPost }>("/api/posts", {
      method: "POST",
      body: JSON.stringify(input),
    }).then((r) => r.post),

  deletePost: (id: string) =>
    request<void>(`/api/posts/${id}`, { method: "DELETE" }),

  validatePost: (input: PostInput) =>
    request<{ issues: ValidationIssue[] }>("/api/posts/validate", {
      method: "POST",
      body: JSON.stringify(input),
    }).then((r) => r.issues),

  publishPost: (id: string) =>
    request<{ post: UniversalPost; issues: ValidationIssue[] }>(
      `/api/posts/${id}/publish`,
      { method: "POST" }
    ),

  listConnections: () =>
    request<{ connections: ConnectionInfo[] }>("/api/connections").then(
      (r) => r.connections
    ),

  connect: (platform: SnsPlatform, handle?: string) =>
    request<{ connection: ConnectionInfo }>(
      `/api/connections/${platform}/connect`,
      { method: "POST", body: JSON.stringify({ handle }) }
    ).then((r) => r.connection),

  disconnect: (platform: SnsPlatform) =>
    request<{ connection: ConnectionInfo }>(
      `/api/connections/${platform}/disconnect`,
      { method: "POST" }
    ).then((r) => r.connection),
};
