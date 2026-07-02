import { randomUUID } from "node:crypto";
import {
  PLATFORMS,
  type ConnectionInfo,
  type Platform,
  type PostInput,
  type UniversalPost,
} from "@crosspost/shared";

/**
 * In-memory persistence for the MVP. Swap for a database (e.g. Postgres via
 * Drizzle/Prisma) without touching routes — this module is the only owner
 * of state.
 */

const posts = new Map<string, UniversalPost>();

const connections = new Map<Platform, ConnectionInfo>(
  PLATFORMS.map((p) => [p, { platform: p, connected: false }])
);

export const postStore = {
  list(): UniversalPost[] {
    return [...posts.values()].sort((a, b) =>
      b.createdAt.localeCompare(a.createdAt)
    );
  },

  get(id: string): UniversalPost | undefined {
    return posts.get(id);
  },

  create(input: PostInput): UniversalPost {
    const now = new Date().toISOString();
    const post: UniversalPost = {
      id: randomUUID(),
      text: input.text,
      media: input.media ?? [],
      targets: input.targets ?? [],
      status: "draft",
      createdAt: now,
      updatedAt: now,
      results: [],
    };
    posts.set(post.id, post);
    return post;
  },

  update(id: string, patch: Partial<UniversalPost>): UniversalPost | undefined {
    const existing = posts.get(id);
    if (!existing) return undefined;
    const updated: UniversalPost = {
      ...existing,
      ...patch,
      id: existing.id,
      updatedAt: new Date().toISOString(),
    };
    posts.set(id, updated);
    return updated;
  },

  delete(id: string): boolean {
    return posts.delete(id);
  },
};

export const connectionStore = {
  list(): ConnectionInfo[] {
    return PLATFORMS.map((p) => connections.get(p)!);
  },

  get(platform: Platform): ConnectionInfo {
    return connections.get(platform)!;
  },

  connect(platform: Platform, handle: string): ConnectionInfo {
    const info: ConnectionInfo = {
      platform,
      connected: true,
      handle,
      connectedAt: new Date().toISOString(),
    };
    connections.set(platform, info);
    return info;
  },

  disconnect(platform: Platform): ConnectionInfo {
    const info: ConnectionInfo = { platform, connected: false };
    connections.set(platform, info);
    return info;
  },
};
