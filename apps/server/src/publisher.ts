import type {
  Platform,
  PublishResult,
  UniversalPost,
  ValidationIssue,
} from "@crosspost/shared";
import { adapters } from "./platforms/index";
import { connectionStore } from "./store";

export interface PublishOutcome {
  results: PublishResult[];
  issues: ValidationIssue[];
}

/**
 * Fan a universal post out to every selected platform. Each target is
 * validated against its platform's post model, transformed into the
 * platform-native payload, and published independently — one platform
 * failing doesn't block the others.
 */
export async function publishToTargets(
  post: UniversalPost
): Promise<PublishOutcome> {
  const issues: ValidationIssue[] = [];

  const results = await Promise.all(
    post.targets.map(async (platform): Promise<PublishResult> => {
      if (!connectionStore.get(platform).connected) {
        const issue: ValidationIssue = {
          platform,
          code: "NOT_CONNECTED",
          message: `${platform} account is not connected.`,
        };
        issues.push(issue);
        return { platform, status: "skipped", error: issue.message };
      }

      const adapter = adapters[platform];
      const platformIssues = adapter.validate(post);
      if (platformIssues.length > 0) {
        issues.push(...platformIssues);
        return {
          platform,
          status: "failed",
          error: platformIssues.map((i) => i.message).join(" "),
        };
      }

      try {
        const payload = adapter.toPayload(post);
        return await adapter.publish(post, payload);
      } catch (err) {
        return {
          platform,
          status: "failed",
          error: err instanceof Error ? err.message : String(err),
        };
      }
    })
  );

  return { results, issues };
}

export function overallStatus(
  results: PublishResult[]
): UniversalPost["status"] {
  return results.some((r) => r.status === "published")
    ? "published"
    : "failed";
}
