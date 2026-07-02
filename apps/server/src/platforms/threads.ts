import {
  validateForPlatform,
  type PublishResult,
  type ThreadsPayload,
  type UniversalPost,
} from "@crosspost/shared";
import { simulateRemotePublish, type PlatformAdapter } from "./adapter";

/**
 * Threads API adapter.
 * Native model: a media container (TEXT | IMAGE | VIDEO | CAROUSEL) created
 * via POST /{threads-user-id}/threads and published via /threads_publish.
 */
export const threadsAdapter: PlatformAdapter<ThreadsPayload> = {
  platform: "threads",

  validate(post) {
    return validateForPlatform("threads", post);
  },

  toPayload(post) {
    const text = post.text.slice(0, 500);

    if (post.media.length === 0) {
      return { media_type: "TEXT", text };
    }

    if (post.media.length === 1) {
      const asset = post.media[0];
      return asset.type === "video"
        ? { media_type: "VIDEO", text, video_url: asset.url }
        : { media_type: "IMAGE", text, image_url: asset.url };
    }

    return {
      media_type: "CAROUSEL",
      text,
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
      "threads",
      (id) => `https://www.threads.net/@me/post/${id}`
    );
    return { platform: "threads", status: "published", payload, ...remote };
  },
};
