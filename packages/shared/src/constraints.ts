import type {
  MediaAsset,
  Platform,
  PostInput,
  ValidationIssue,
} from "./types";

/**
 * Publishing constraints per platform, mirroring each SNS API's post model.
 * Used by the mobile composer for live feedback and by the server as the
 * source of truth before transforming to platform payloads.
 */
export interface PlatformConstraints {
  /** Human-readable name, e.g. "X (Twitter)". */
  label: string;
  maxTextLength: number;
  /** Post must include at least one media asset. */
  mediaRequired: boolean;
  /** Post must include a video (e.g. TikTok). */
  videoRequired: boolean;
  maxImages: number;
  maxVideos: number;
  /** Max total media items in a single post/carousel. */
  maxMedia: number;
  /** Images and videos allowed together in one post. */
  allowsMixedMedia: boolean;
  maxHashtags?: number;
  /** Text-only posts allowed. */
  allowsTextOnly: boolean;
}

export const PLATFORM_CONSTRAINTS: Record<Platform, PlatformConstraints> = {
  instagram: {
    label: "Instagram",
    maxTextLength: 2200, // caption limit
    mediaRequired: true,
    videoRequired: false,
    maxImages: 10,
    maxVideos: 10,
    maxMedia: 10, // carousel limit
    allowsMixedMedia: true,
    maxHashtags: 30,
    allowsTextOnly: false,
  },
  facebook: {
    label: "Facebook",
    maxTextLength: 63206,
    mediaRequired: false,
    videoRequired: false,
    maxImages: 10,
    maxVideos: 1,
    maxMedia: 10,
    allowsMixedMedia: false,
    allowsTextOnly: true,
  },
  threads: {
    label: "Threads",
    maxTextLength: 500,
    mediaRequired: false,
    videoRequired: false,
    maxImages: 20,
    maxVideos: 20,
    maxMedia: 20, // carousel limit
    allowsMixedMedia: true,
    allowsTextOnly: true,
  },
  x: {
    label: "X (Twitter)",
    maxTextLength: 280,
    mediaRequired: false,
    videoRequired: false,
    maxImages: 4,
    maxVideos: 1,
    maxMedia: 4,
    allowsMixedMedia: false, // one video XOR up to 4 images
    allowsTextOnly: true,
  },
  tiktok: {
    label: "TikTok",
    maxTextLength: 2200, // video caption limit
    mediaRequired: true,
    videoRequired: true,
    maxImages: 0,
    maxVideos: 1,
    maxMedia: 1,
    allowsMixedMedia: false,
    allowsTextOnly: false,
  },
};

export function countHashtags(text: string): number {
  return (text.match(/#[\p{L}\p{N}_]+/gu) ?? []).length;
}

function mediaCounts(media: MediaAsset[]) {
  const images = media.filter((m) => m.type === "image").length;
  const videos = media.filter((m) => m.type === "video").length;
  return { images, videos, total: media.length };
}

/**
 * Validate a composed post against one platform's post model.
 * Returns an empty array when the post is publishable as-is.
 */
export function validateForPlatform(
  platform: Platform,
  post: PostInput
): ValidationIssue[] {
  const c = PLATFORM_CONSTRAINTS[platform];
  const media = post.media ?? [];
  const { images, videos, total } = mediaCounts(media);
  const issues: ValidationIssue[] = [];

  if (post.text.length > c.maxTextLength) {
    issues.push({
      platform,
      code: "TEXT_TOO_LONG",
      message: `${c.label} allows up to ${c.maxTextLength.toLocaleString()} characters (currently ${post.text.length.toLocaleString()}).`,
    });
  }

  if (c.videoRequired && videos === 0) {
    issues.push({
      platform,
      code: "VIDEO_REQUIRED",
      message: `${c.label} posts require a video.`,
    });
  } else if (c.mediaRequired && total === 0) {
    issues.push({
      platform,
      code: "MEDIA_REQUIRED",
      message: `${c.label} posts require at least one image or video.`,
    });
  }

  if (total > c.maxMedia) {
    issues.push({
      platform,
      code: "TOO_MANY_MEDIA",
      message: `${c.label} allows at most ${c.maxMedia} media item${c.maxMedia === 1 ? "" : "s"} per post.`,
    });
  } else if (images > c.maxImages || videos > c.maxVideos) {
    issues.push({
      platform,
      code: "TOO_MANY_MEDIA",
      message: `${c.label} allows at most ${c.maxImages} image${c.maxImages === 1 ? "" : "s"} and ${c.maxVideos} video${c.maxVideos === 1 ? "" : "s"} per post.`,
    });
  }

  if (!c.allowsMixedMedia && images > 0 && videos > 0) {
    issues.push({
      platform,
      code: "MIXED_MEDIA_UNSUPPORTED",
      message: `${c.label} doesn't support mixing images and videos in one post.`,
    });
  }

  if (c.maxHashtags !== undefined && countHashtags(post.text) > c.maxHashtags) {
    issues.push({
      platform,
      code: "TOO_MANY_HASHTAGS",
      message: `${c.label} allows at most ${c.maxHashtags} hashtags.`,
    });
  }

  return issues;
}

/** Validate a post against every selected target platform. */
export function validateForTargets(post: PostInput): ValidationIssue[] {
  return (post.targets ?? []).flatMap((p) => validateForPlatform(p, post));
}
