import {
  validateForPlatform,
  type PublishResult,
  type UniversalPost,
  type XPayload,
} from "@crosspost/shared";
import { simulateRemotePublish, type PlatformAdapter } from "./adapter";

/**
 * X (Twitter) API v2 adapter.
 * Native model: POST /2/tweets with `text` and optional `media.media_ids`
 * (media is uploaded first via the media upload endpoint, which returns ids).
 */
export const xAdapter: PlatformAdapter<XPayload> = {
  platform: "x",

  validate(post) {
    return validateForPlatform("x", post);
  },

  toPayload(post) {
    const payload: XPayload = { text: post.text.slice(0, 280) };
    if (post.media.length > 0) {
      // In a real integration each asset is uploaded to X first and the
      // returned media_id is used here.
      payload.media = { media_ids: post.media.map((m) => m.id) };
    }
    return payload;
  },

  async publish(_post, payload): Promise<PublishResult> {
    const remote = simulateRemotePublish(
      "x",
      (id) => `https://x.com/i/status/${id}`
    );
    return { platform: "x", status: "published", payload, ...remote };
  },
};
