/**
 * Native post payload shapes for each SNS API. Platform adapters on the
 * server transform a UniversalPost into one of these before publishing.
 */

/**
 * Instagram Graph API — content publishing.
 * POST /{ig-user-id}/media then /{ig-user-id}/media_publish
 */
export interface InstagramPayload {
  media_type: "IMAGE" | "REELS" | "CAROUSEL";
  caption: string;
  image_url?: string;
  video_url?: string;
  /** Container ids of carousel items. */
  children?: InstagramCarouselChild[];
}

export interface InstagramCarouselChild {
  media_type: "IMAGE" | "VIDEO";
  image_url?: string;
  video_url?: string;
  is_carousel_item: true;
}

/**
 * Facebook Graph API — Page publishing.
 * POST /{page-id}/feed | /{page-id}/photos | /{page-id}/videos
 */
export interface FacebookPayload {
  endpoint: "feed" | "photos" | "videos";
  message?: string;
  /** photos endpoint */
  url?: string;
  /** videos endpoint */
  file_url?: string;
  description?: string;
  /** feed endpoint: attach previously uploaded photos */
  attached_media?: Array<{ media_fbid: string }>;
}

/**
 * Threads API — content publishing.
 * POST /{threads-user-id}/threads then /threads_publish
 */
export interface ThreadsPayload {
  media_type: "TEXT" | "IMAGE" | "VIDEO" | "CAROUSEL";
  text?: string;
  image_url?: string;
  video_url?: string;
  /** Container ids of carousel items. */
  children?: ThreadsCarouselChild[];
}

export interface ThreadsCarouselChild {
  media_type: "IMAGE" | "VIDEO";
  image_url?: string;
  video_url?: string;
  is_carousel_item: true;
}

/**
 * X API v2 — create post.
 * POST /2/tweets (media uploaded separately via media upload endpoint)
 */
export interface XPayload {
  text: string;
  media?: {
    media_ids: string[];
  };
}

/**
 * TikTok Content Posting API — direct post.
 * POST /v2/post/publish/video/init/
 */
export interface TikTokPayload {
  post_info: {
    title: string;
    privacy_level:
      | "PUBLIC_TO_EVERYONE"
      | "MUTUAL_FOLLOW_FRIENDS"
      | "SELF_ONLY";
    disable_duet: boolean;
    disable_comment: boolean;
    disable_stitch: boolean;
  };
  source_info: {
    source: "PULL_FROM_URL";
    video_url: string;
  };
}

export type PlatformPayload =
  | InstagramPayload
  | FacebookPayload
  | ThreadsPayload
  | XPayload
  | TikTokPayload;
