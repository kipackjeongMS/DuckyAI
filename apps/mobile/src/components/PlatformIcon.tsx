import { FontAwesome6 } from "@expo/vector-icons";
import type { Platform } from "@crosspost/shared";

const ICON_NAMES: Record<Platform, string> = {
  instagram: "instagram",
  facebook: "facebook",
  threads: "threads",
  x: "x-twitter",
  tiktok: "tiktok",
};

export function PlatformIcon({
  platform,
  size = 18,
  color = "#000",
}: {
  platform: Platform;
  size?: number;
  color?: string;
}) {
  return (
    <FontAwesome6 name={ICON_NAMES[platform] as any} size={size} color={color} />
  );
}
