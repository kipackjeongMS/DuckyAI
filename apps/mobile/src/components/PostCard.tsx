import { Image } from "expo-image";
import { ScrollView, StyleSheet, Text, View } from "react-native";
import type { PublishResult, UniversalPost } from "@crosspost/shared";
import { useTheme } from "@/theme";
import { PlatformIcon } from "./PlatformIcon";

function timeAgo(iso: string): string {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function resultColor(
  status: PublishResult["status"] | undefined,
  theme: ReturnType<typeof useTheme>
) {
  if (status === "published") return theme.success;
  if (status === "failed") return theme.danger;
  return theme.textSecondary;
}

const STATUS_LABEL: Record<UniversalPost["status"], string> = {
  draft: "Draft",
  publishing: "Publishing…",
  published: "Published",
  failed: "Failed",
};

/**
 * Threads-style feed row: avatar rail on the left, content on the right,
 * hairline divider below. Shows per-platform publish state as icons.
 */
export function PostCard({ post }: { post: UniversalPost }) {
  const theme = useTheme();
  const resultByPlatform = new Map(post.results.map((r) => [r.platform, r]));

  return (
    <View style={[styles.row, { borderBottomColor: theme.border }]}>
      <View style={[styles.avatar, { backgroundColor: theme.border }]}>
        <Text style={[styles.avatarGlyph, { color: theme.textSecondary }]}>
          ✎
        </Text>
      </View>

      <View style={styles.body}>
        <View style={styles.header}>
          <Text style={[styles.status, { color: theme.text }]}>
            {STATUS_LABEL[post.status]}
          </Text>
          <Text style={[styles.time, { color: theme.textSecondary }]}>
            {timeAgo(post.createdAt)}
          </Text>
        </View>

        {post.text.length > 0 && (
          <Text style={[styles.text, { color: theme.text }]}>{post.text}</Text>
        )}

        {post.media.length > 0 && (
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.mediaRow}
          >
            {post.media.map((asset) => (
              <View
                key={asset.id}
                style={[styles.media, { backgroundColor: theme.border }]}
              >
                {asset.type === "image" ? (
                  <Image
                    source={{ uri: asset.url }}
                    style={StyleSheet.absoluteFill}
                    contentFit="cover"
                  />
                ) : (
                  <Text style={{ color: theme.textSecondary, fontSize: 24 }}>
                    ▶
                  </Text>
                )}
              </View>
            ))}
          </ScrollView>
        )}

        <View style={styles.platforms}>
          {post.targets.map((platform) => {
            const result = resultByPlatform.get(platform);
            return (
              <View key={platform} style={styles.platform}>
                <PlatformIcon
                  platform={platform}
                  size={14}
                  color={resultColor(result?.status, theme)}
                />
              </View>
            );
          })}
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: "row",
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 12,
  },
  avatar: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: "center",
    justifyContent: "center",
  },
  avatarGlyph: { fontSize: 16 },
  body: { flex: 1, gap: 8 },
  header: { flexDirection: "row", justifyContent: "space-between" },
  status: { fontSize: 15, fontWeight: "600" },
  time: { fontSize: 14 },
  text: { fontSize: 15, lineHeight: 21 },
  mediaRow: { marginTop: 2 },
  media: {
    width: 140,
    height: 180,
    borderRadius: 12,
    marginRight: 8,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  platforms: { flexDirection: "row", gap: 12, marginTop: 2 },
  platform: { opacity: 0.9 },
});
