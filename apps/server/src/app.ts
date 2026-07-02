import cors from "@fastify/cors";
import Fastify from "fastify";
import { connectionRoutes } from "./routes/connections";
import { postRoutes } from "./routes/posts";

export function buildApp() {
  const app = Fastify({ logger: true });

  app.register(cors, { origin: true });

  app.get("/health", async () => ({ status: "ok" }));

  app.register(postRoutes);
  app.register(connectionRoutes);

  return app;
}
