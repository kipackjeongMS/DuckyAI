import {
  validateForPlatform,
  type PublishResult,
  type TikTokPayload,
  type UniversalPost,
} from "@crosspost/shared";
import { simulateRemotePublish, type PlatformAdapter } from "./adapter";

/**
 * TikTok Content Posting API adapter.
 * Native model: POST /v2/post/publish/video/init/ with `post_info` (title,
 * privacy, interaction toggles) and `source_info` (video pulled from a URL).
 * TikTok posts are video-only.
 */
export const tiktokAdapter: PlatformAdapter<TikTokPayload> = {
  platform: "tiktok",

  validate(post) {
    return validateForPlatform("tiktok", post);
  },

  toPayload(post) {
    const video = post.media.find((m) => m.type === "video");
    if (!video) {
      throw new Error("TikTok posts require a video");
    }
    return {
      post_info: {
        title: post.text.slice(0, 2200),
        privacy_level: "PUBLIC_TO_EVERYONE",
        disable_duet: false,
        disable_comment: false,
        disable_stitch: false,
      },
      source_info: {
        source: "PULL_FROM_URL",
        video_url: video.url,
      },
    };
  },

  async publish(_post, payload): Promise<PublishResult> {
    const remote = simulateRemotePublish(
      "tiktok",
      (id) => `https://www.tiktok.com/@me/video/${id}`
    );
    return { platform: "tiktok", status: "published", payload, ...remote };
  },
};
