import {
  validateForPlatform,
  type FacebookPayload,
  type PublishResult,
  type UniversalPost,
} from "@crosspost/shared";
import { simulateRemotePublish, type PlatformAdapter } from "./adapter";

/**
 * Facebook Graph API adapter (Page publishing).
 * Native model: text posts go to /{page-id}/feed as `message`; a photo goes
 * to /photos with `url`; a video goes to /videos with `file_url`.
 */
export const facebookAdapter: PlatformAdapter<FacebookPayload> = {
  platform: "facebook",

  validate(post) {
    return validateForPlatform("facebook", post);
  },

  toPayload(post) {
    const video = post.media.find((m) => m.type === "video");
    if (video) {
      return {
        endpoint: "videos",
        file_url: video.url,
        description: post.text,
      };
    }

    const images = post.media.filter((m) => m.type === "image");
    if (images.length === 1) {
      return { endpoint: "photos", url: images[0].url, message: post.text };
    }
    if (images.length > 1) {
      // Multi-photo posts attach pre-uploaded photos to a feed post.
      return {
        endpoint: "feed",
        message: post.text,
        attached_media: images.map((img) => ({ media_fbid: img.id })),
      };
    }

    return { endpoint: "feed", message: post.text };
  },

  async publish(_post, payload): Promise<PublishResult> {
    const remote = simulateRemotePublish(
      "facebook",
      (id) => `https://www.facebook.com/${id}`
    );
    return { platform: "facebook", status: "published", payload, ...remote };
  },
};
