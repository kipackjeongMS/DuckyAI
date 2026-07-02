import type { FastifyInstance } from "fastify";
import {
  PLATFORMS,
  validateForTargets,
  type PostInput,
} from "@crosspost/shared";
import { overallStatus, publishToTargets } from "../publisher";
import { postStore } from "../store";

const mediaAssetSchema = {
  type: "object",
  required: ["id", "type", "url"],
  properties: {
    id: { type: "string" },
    type: { type: "string", enum: ["image", "video"] },
    url: { type: "string" },
    width: { type: "number" },
    height: { type: "number" },
    durationSec: { type: "number" },
    mimeType: { type: "string" },
  },
} as const;

const postInputSchema = {
  type: "object",
  required: ["text"],
  properties: {
    text: { type: "string" },
    media: { type: "array", items: mediaAssetSchema },
    targets: {
      type: "array",
      items: { type: "string", enum: [...PLATFORMS] },
    },
  },
} as const;

export async function postRoutes(app: FastifyInstance) {
  app.get("/api/posts", async () => ({ posts: postStore.list() }));

  app.get("/api/posts/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    const post = postStore.get(id);
    if (!post) return reply.code(404).send({ error: "Post not found" });
    return { post };
  });

  app.post(
    "/api/posts",
    { schema: { body: postInputSchema } },
    async (req, reply) => {
      const input = req.body as PostInput;
      const post = postStore.create(input);
      return reply.code(201).send({ post });
    }
  );

  app.patch(
    "/api/posts/:id",
    { schema: { body: postInputSchema } },
    async (req, reply) => {
      const { id } = req.params as { id: string };
      const input = req.body as PostInput;
      const post = postStore.update(id, {
        text: input.text,
        media: input.media ?? [],
        targets: input.targets ?? [],
      });
      if (!post) return reply.code(404).send({ error: "Post not found" });
      return { post };
    }
  );

  app.delete("/api/posts/:id", async (req, reply) => {
    const { id } = req.params as { id: string };
    if (!postStore.delete(id)) {
      return reply.code(404).send({ error: "Post not found" });
    }
    return reply.code(204).send();
  });

  /**
   * Dry-run validation: check a draft against each selected platform's
   * post model without publishing. The composer calls this live.
   */
  app.post(
    "/api/posts/validate",
    { schema: { body: postInputSchema } },
    async (req) => {
      const input = req.body as PostInput;
      return { issues: validateForTargets(input) };
    }
  );

  /** Publish a draft to all of its target platforms. */
  app.post("/api/posts/:id/publish", async (req, reply) => {
    const { id } = req.params as { id: string };
    const post = postStore.get(id);
    if (!post) return reply.code(404).send({ error: "Post not found" });
    if (post.targets.length === 0) {
      return reply
        .code(400)
        .send({ error: "Select at least one platform to publish to." });
    }
    if (post.status === "publishing") {
      return reply.code(409).send({ error: "Post is already publishing." });
    }

    postStore.update(id, { status: "publishing" });
    const { results, issues } = await publishToTargets(post);
    const updated = postStore.update(id, {
      status: overallStatus(results),
      results,
    });

    return { post: updated, issues };
  });
}
