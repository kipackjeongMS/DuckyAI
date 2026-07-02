import type { FastifyInstance } from "fastify";
import { PLATFORMS, type Platform } from "@crosspost/shared";
import { connectionStore } from "../store";

function parsePlatform(value: string): Platform | undefined {
  return (PLATFORMS as readonly string[]).includes(value)
    ? (value as Platform)
    : undefined;
}

export async function connectionRoutes(app: FastifyInstance) {
  app.get("/api/connections", async () => ({
    connections: connectionStore.list(),
  }));

  /**
   * Simulated OAuth connect. A real integration redirects the user through
   * the platform's OAuth flow and stores the resulting tokens server-side;
   * here we just mark the account connected with a demo handle.
   */
  app.post("/api/connections/:platform/connect", async (req, reply) => {
    const { platform: raw } = req.params as { platform: string };
    const platform = parsePlatform(raw);
    if (!platform) {
      return reply.code(400).send({ error: `Unknown platform: ${raw}` });
    }
    const { handle } = (req.body ?? {}) as { handle?: string };
    return {
      connection: connectionStore.connect(platform, handle || "@ducky"),
    };
  });

  app.post("/api/connections/:platform/disconnect", async (req, reply) => {
    const { platform: raw } = req.params as { platform: string };
    const platform = parsePlatform(raw);
    if (!platform) {
      return reply.code(400).send({ error: `Unknown platform: ${raw}` });
    }
    return { connection: connectionStore.disconnect(platform) };
  });
}
