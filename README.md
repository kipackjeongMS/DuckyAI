# CrossPost

Write once, publish everywhere. CrossPost is a SNS content creation hub:
compose a post (text, images, video) in one place and shoot it out to
**Instagram, Facebook, Threads, X (Twitter), and TikTok** — each publish
transformed into that platform's native post data model.

The UI mirrors the Threads design language: near-monochrome, hairline
dividers, pill buttons, generous whitespace, automatic light/dark mode.

## Stack

| Layer  | Tech |
| ------ | ---- |
| Mobile | React Native + Expo (SDK 53), expo-router, EAS for builds |
| API    | Fastify 5 (Node 20+, TypeScript) |
| Shared | `@crosspost/shared` — universal post model, platform constraints, native payload types |

Monorepo layout (npm workspaces):

```
apps/
  mobile/     Expo app (expo-router screens, Threads-style UI, eas.json)
  server/     Fastify API (routes, platform adapters, in-memory store)
packages/
  shared/     Types + per-platform validation shared by both
```

## How cross-posting works

1. The composer validates your draft **live** against every selected
   platform's rules (`packages/shared/src/constraints.ts`) — e.g. X caps at
   280 chars, Threads at 500, Instagram requires media, TikTok requires a
   video — and shows the tightest character budget.
2. On publish, the server fans the post out to one **adapter per platform**
   (`apps/server/src/platforms/`). Each adapter transforms the universal
   post into the platform's native payload:
   - **Instagram** → Graph API media container (`IMAGE` / `REELS` / `CAROUSEL` + caption)
   - **Facebook** → Page publishing (`feed` message / `photos` url / `videos` file_url)
   - **Threads** → Threads API container (`TEXT` / `IMAGE` / `VIDEO` / `CAROUSEL`)
   - **X (Twitter)** → `POST /2/tweets` (`text` + `media.media_ids`)
   - **TikTok** → Content Posting API (`post_info` + `source_info.video_url`)
3. Platforms publish independently — one failing doesn't block the rest —
   and per-platform results (id, permalink, error) come back on the post.

The actual remote API calls are simulated (`simulateRemotePublish`) so the
whole flow runs locally with zero credentials. Real integrations plug into
each adapter's `publish()` plus an OAuth flow in
`apps/server/src/routes/connections.ts`.

> Note: X and Twitter are the same platform (Twitter rebranded to X), so
> they're one integration here.

## Getting started

```bash
npm install

# 1. API (http://localhost:4000)
npm run dev:server

# 2. Expo app (press i / a, or scan the QR with Expo Go)
npm run dev:mobile
```

In the app: **Accounts** tab → connect platforms (simulated OAuth) →
**✎** tab → write, attach media, pick targets, Post.

The app targets `http://localhost:4000` by default (`10.0.2.2` on Android
emulators). Point it elsewhere with `EXPO_PUBLIC_API_URL`.

## Tests & typecheck

```bash
npm run typecheck          # all workspaces
npm test                   # server: publish fan-out + payload mapping tests
```

## EAS builds

`apps/mobile/eas.json` defines `development`, `preview`, and `production`
profiles. After `npm i -g eas-cli && eas login`:

```bash
cd apps/mobile
eas init                   # sets your real projectId in app.json
eas build --profile preview --platform all
```

Each profile injects `EXPO_PUBLIC_API_URL` for its environment — replace
the staging/production URLs with your deployed API.
