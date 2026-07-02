import assert from "node:assert/strict";
import test from "node:test";
import { buildApp } from "../src/app";

async function connectAll(app: ReturnType<typeof buildApp>) {
  for (const p of ["instagram", "facebook", "threads", "x", "tiktok"]) {
    await app.inject({
      method: "POST",
      url: `/api/connections/${p}/connect`,
      payload: { handle: "@test" },
    });
  }
}

test("text-only post publishes to text platforms with native payloads", async () => {
  const app = buildApp();
  await connectAll(app);

  const created = await app.inject({
    method: "POST",
    url: "/api/posts",
    payload: { text: "Hello world", targets: ["threads", "x", "facebook"] },
  });
  assert.equal(created.statusCode, 201);
  const { post } = created.json();

  const published = await app.inject({
    method: "POST",
    url: `/api/posts/${post.id}/publish`,
  });
  assert.equal(published.statusCode, 200);
  const body = published.json();
  assert.equal(body.post.status, "published");

  const byPlatform = Object.fromEntries(
    body.post.results.map((r: any) => [r.platform, r])
  );
  assert.equal(byPlatform.threads.payload.media_type, "TEXT");
  assert.equal(byPlatform.threads.payload.text, "Hello world");
  assert.equal(byPlatform.x.payload.text, "Hello world");
  assert.equal(byPlatform.facebook.payload.endpoint, "feed");
  assert.equal(byPlatform.facebook.payload.message, "Hello world");
});

test("text-only post fails platform models that require media", async () => {
  const app = buildApp();
  await connectAll(app);

  const created = await app.inject({
    method: "POST",
    url: "/api/posts",
    payload: { text: "No media here", targets: ["instagram", "tiktok", "x"] },
  });
  const { post } = created.json();

  const published = await app.inject({
    method: "POST",
    url: `/api/posts/${post.id}/publish`,
  });
  const body = published.json();

  const byPlatform = Object.fromEntries(
    body.post.results.map((r: any) => [r.platform, r])
  );
  assert.equal(byPlatform.instagram.status, "failed");
  assert.equal(byPlatform.tiktok.status, "failed");
  assert.equal(byPlatform.x.status, "published");
  // partial success still counts as published overall
  assert.equal(body.post.status, "published");
  const codes = body.issues.map((i: any) => i.code);
  assert.ok(codes.includes("MEDIA_REQUIRED"));
  assert.ok(codes.includes("VIDEO_REQUIRED"));
});

test("video post maps to each platform's native video shape", async () => {
  const app = buildApp();
  await connectAll(app);

  const video = {
    id: "vid1",
    type: "video",
    url: "https://cdn.example.com/clip.mp4",
  };
  const created = await app.inject({
    method: "POST",
    url: "/api/posts",
    payload: {
      text: "Watch this",
      media: [video],
      targets: ["instagram", "tiktok", "facebook"],
    },
  });
  const { post } = created.json();

  const published = await app.inject({
    method: "POST",
    url: `/api/posts/${post.id}/publish`,
  });
  const body = published.json();
  const byPlatform = Object.fromEntries(
    body.post.results.map((r: any) => [r.platform, r])
  );

  assert.equal(byPlatform.instagram.payload.media_type, "REELS");
  assert.equal(byPlatform.instagram.payload.video_url, video.url);
  assert.equal(byPlatform.tiktok.payload.source_info.video_url, video.url);
  assert.equal(byPlatform.tiktok.payload.post_info.title, "Watch this");
  assert.equal(byPlatform.facebook.payload.endpoint, "videos");
  assert.equal(byPlatform.facebook.payload.file_url, video.url);
});

test("unconnected platforms are skipped, not failed", async () => {
  const app = buildApp();
  // the store is process-wide, so explicitly disconnect x
  await app.inject({ method: "POST", url: "/api/connections/x/disconnect" });

  const created = await app.inject({
    method: "POST",
    url: "/api/posts",
    payload: { text: "hi", targets: ["x"] },
  });
  const { post } = created.json();

  const published = await app.inject({
    method: "POST",
    url: `/api/posts/${post.id}/publish`,
  });
  const body = published.json();
  assert.equal(body.post.results[0].status, "skipped");
  assert.equal(body.post.status, "failed");
});

test("validate endpoint flags text over the tightest limit", async () => {
  const app = buildApp();
  const res = await app.inject({
    method: "POST",
    url: "/api/posts/validate",
    payload: { text: "a".repeat(300), targets: ["x", "threads"] },
  });
  const { issues } = res.json();
  assert.equal(issues.length, 1);
  assert.equal(issues[0].platform, "x");
  assert.equal(issues[0].code, "TEXT_TOO_LONG");
});
