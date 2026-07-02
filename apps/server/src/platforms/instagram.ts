import {
  validateForPlatform,
  type InstagramPayload,
  type PublishResult,
  type UniversalPost,
} from "@crosspost/shared";
import { simulateRemotePublish, type PlatformAdapter } from "./adapter";

/**
 * Instagram Graph API adapter.
 * Native model: a media container (IMAGE | REELS | CAROUSEL) with a caption,
 * created via POST /{ig-user-id}/media and published via /media_publish.
 * Instagram has no text-only posts — media is mandatory.
 */
export const instagramAdapter: PlatformAdapter<InstagramPayload> = {
  platform: "instagram",

  validate(post) {
    return validateForPlatform("instagram", post);
  },

  toPayload(post) {
    const caption = post.text.slice(0, 2200);

    if (post.media.length === 1) {
      const asset = post.media[0];
      if (asset.type === "video") {
        // Single videos publish as Reels on the current Graph API.
        return { media_type: "REELS", caption, video_url: asset.url };
      }
      return { media_type: "IMAGE", caption, image_url: asset.url };
    }

    return {
      media_type: "CAROUSEL",
      caption,
      children: post.media.map((asset) => ({
        media_type: asset.type === "video" ? "VIDEO" : "IMAGE",
        ...(asset.type === "video"
          ? { video_url: asset.url }
          : { image_url: asset.url }),
        is_carousel_item: true as const,
      })),
    };
  },

  async publish(_post, payload): Promise<PublishResult> {
    const remote = simulateRemotePublish(
      "instagram",
      (id) => `https://www.instagram.com/p/${id}/`
    );
    return { platform: "instagram", status: "published", payload, ...remote };
  },
};
