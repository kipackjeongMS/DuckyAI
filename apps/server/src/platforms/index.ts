import type { Platform } from "@crosspost/shared";
import type { PlatformAdapter } from "./adapter";
import { facebookAdapter } from "./facebook";
import { instagramAdapter } from "./instagram";
import { threadsAdapter } from "./threads";
import { tiktokAdapter } from "./tiktok";
import { xAdapter } from "./x";

export const adapters: Record<Platform, PlatformAdapter<any>> = {
  instagram: instagramAdapter,
  facebook: facebookAdapter,
  threads: threadsAdapter,
  x: xAdapter,
  tiktok: tiktokAdapter,
};

export type { PlatformAdapter } from "./adapter";
