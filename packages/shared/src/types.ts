/**
 * Universal post model — what the user composes in CrossPost.
 * Platform adapters transform this into each SNS's native post shape.
 */

export const PLATFORMS = [
  "instagram",
  "facebook",
  "threads",
  "x",
  "tiktok",
] as const;

export type Platform = (typeof PLATFORMS)[number];

export type MediaType = "image" | "video";

export interface MediaAsset {
  id: string;
  type: MediaType;
  /** Publicly reachable URL (platform APIs ingest media by URL). */
  url: string;
  width?: number;
  height?: number;
  /** Video duration in seconds, when known. */
  durationSec?: number;
  mimeType?: string;
}

export type PostStatus = "draft" | "publishing" | "published" | "failed";

export interface UniversalPost {
  id: string;
  text: string;
  media: MediaAsset[];
  /** Platforms the user selected as publish targets. */
  targets: Platform[];
  status: PostStatus;
  createdAt: string;
  updatedAt: string;
  /** Per-platform outcome after a publish attempt. */
  results: PublishResult[];
}

export interface PublishResult {
  platform: Platform;
  status: "published" | "failed" | "skipped";
  /** Platform-native id of the created post, when published. */
  remoteId?: string;
  /** Permalink to the post on the platform, when available. */
  remoteUrl?: string;
  error?: string;
  /** The platform-specific payload that was (or would be) sent. */
  payload?: unknown;
  publishedAt?: string;
}

export interface ValidationIssue {
  platform: Platform;
  code:
    | "TEXT_TOO_LONG"
    | "MEDIA_REQUIRED"
    | "VIDEO_REQUIRED"
    | "TOO_MANY_MEDIA"
    | "MIXED_MEDIA_UNSUPPORTED"
    | "TOO_MANY_HASHTAGS"
    | "NOT_CONNECTED";
  message: string;
}

export interface ConnectionInfo {
  platform: Platform;
  connected: boolean;
  /** Display handle of the connected account, e.g. "@ducky". */
  handle?: string;
  connectedAt?: string;
}

/** Input body for creating/updating a draft. */
export interface PostInput {
  text: string;
  media?: MediaAsset[];
  targets?: Platform[];
}
