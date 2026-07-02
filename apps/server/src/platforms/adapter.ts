import type {
  Platform,
  PublishResult,
  UniversalPost,
  ValidationIssue,
} from "@crosspost/shared";

/**
 * A platform adapter owns everything specific to one SNS:
 * validating a universal post against the platform's rules, transforming
 * it into the platform's native payload, and publishing it.
 */
export interface PlatformAdapter<TPayload = unknown> {
  platform: Platform;
  /** Check the post against this platform's post model. */
  validate(post: UniversalPost): ValidationIssue[];
  /** Transform the universal post into the platform's native payload. */
  toPayload(post: UniversalPost): TPayload;
  /** Send the payload to the platform API. */
  publish(post: UniversalPost, payload: TPayload): Promise<PublishResult>;
}

let counter = 0;

/**
 * Simulated remote publish. Real integrations plug in here: exchange the
 * stored OAuth token, call the platform API with the payload, and return
 * the platform's post id/permalink.
 */
export function simulateRemotePublish(
  platform: Platform,
  urlTemplate: (id: string) => string
): { remoteId: string; remoteUrl: string; publishedAt: string } {
  counter += 1;
  const remoteId = `${platform}_${Date.now().toString(36)}${counter}`;
  return {
    remoteId,
    remoteUrl: urlTemplate(remoteId),
    publishedAt: new Date().toISOString(),
  };
}
