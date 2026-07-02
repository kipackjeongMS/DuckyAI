import { useCallback, useEffect, useMemo, useState } from "react";
import * as ImagePicker from "expo-image-picker";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform as RNPlatform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  PLATFORMS,
  PLATFORM_CONSTRAINTS,
  validateForTargets,
  type ConnectionInfo,
  type MediaAsset,
  type Platform,
} from "@crosspost/shared";
import { api } from "@/api";
import { PlatformChip } from "@/components/PlatformChip";
import { useTheme } from "@/theme";

export default function ComposeScreen() {
  const theme = useTheme();
  const router = useRouter();

  const [text, setText] = useState("");
  const [media, setMedia] = useState<MediaAsset[]>([]);
  const [targets, setTargets] = useState<Platform[]>([]);
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    api
      .listConnections()
      .then(setConnections)
      .catch(() => setConnections([]));
  }, []);

  const connected = useMemo(
    () => new Set(connections.filter((c) => c.connected).map((c) => c.platform)),
    [connections]
  );

  // Validate locally against each selected platform's post model, live.
  const issues = useMemo(
    () => validateForTargets({ text, media, targets }),
    [text, media, targets]
  );

  // Character budget = tightest limit among the selected platforms.
  const charBudget = useMemo(() => {
    const selected = targets.length > 0 ? targets : [...PLATFORMS];
    const limit = Math.min(
      ...selected.map((p) => PLATFORM_CONSTRAINTS[p].maxTextLength)
    );
    const tightest = selected.reduce((a, b) =>
      PLATFORM_CONSTRAINTS[a].maxTextLength <=
      PLATFORM_CONSTRAINTS[b].maxTextLength
        ? a
        : b
    );
    return { limit, label: PLATFORM_CONSTRAINTS[tightest].label };
  }, [targets]);

  const toggleTarget = useCallback((platform: Platform) => {
    setTargets((prev) =>
      prev.includes(platform)
        ? prev.filter((p) => p !== platform)
        : [...prev, platform]
    );
  }, []);

  const pickMedia = useCallback(async () => {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ["images", "videos"],
      allowsMultipleSelection: true,
      quality: 0.9,
    });
    if (result.canceled) return;
    const picked: MediaAsset[] = result.assets.map((asset, i) => ({
      id: `${Date.now()}_${i}`,
      type: asset.type === "video" ? "video" : "image",
      // Local URI for the MVP; a real deployment uploads the file and
      // passes a public URL, which platform APIs ingest.
      url: asset.uri,
      width: asset.width,
      height: asset.height,
      durationSec: asset.duration ? asset.duration / 1000 : undefined,
      mimeType: asset.mimeType,
    }));
    setMedia((prev) => [...prev, ...picked]);
  }, []);

  const removeMedia = useCallback((id: string) => {
    setMedia((prev) => prev.filter((m) => m.id !== id));
  }, []);

  const canPublish =
    !publishing &&
    targets.length > 0 &&
    issues.length === 0 &&
    (text.trim().length > 0 || media.length > 0);

  const publish = useCallback(async () => {
    setPublishing(true);
    try {
      const post = await api.createPost({ text, media, targets });
      const { post: published } = await api.publishPost(post.id);
      const ok = published.results.filter((r) => r.status === "published");
      const bad = published.results.filter((r) => r.status !== "published");
      const summary = [
        ok.length > 0
          ? `Published to ${ok
              .map((r) => PLATFORM_CONSTRAINTS[r.platform].label)
              .join(", ")}.`
          : null,
        ...bad.map(
          (r) => `${PLATFORM_CONSTRAINTS[r.platform].label}: ${r.error}`
        ),
      ]
        .filter(Boolean)
        .join("\n");
      Alert.alert(ok.length > 0 ? "Posted" : "Publish failed", summary, [
        { text: "OK", onPress: () => router.back() },
      ]);
    } catch (err) {
      Alert.alert(
        "Publish failed",
        err instanceof Error ? err.message : "Try again."
      );
    } finally {
      setPublishing(false);
    }
  }, [text, media, targets, router]);

  const remaining = charBudget.limit - text.length;

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: theme.background }]}
      edges={["top", "bottom"]}
    >
      <KeyboardAvoidingView
        style={styles.container}
        behavior={RNPlatform.OS === "ios" ? "padding" : undefined}
      >
        <View style={[styles.header, { borderBottomColor: theme.border }]}>
          <Pressable onPress={() => router.back()} hitSlop={12}>
            <Text style={[styles.cancel, { color: theme.text }]}>Cancel</Text>
          </Pressable>
          <Text style={[styles.headerTitle, { color: theme.text }]}>
            New post
          </Text>
          <Pressable
            onPress={publish}
            disabled={!canPublish}
            style={[
              styles.postButton,
              { backgroundColor: theme.primary, opacity: canPublish ? 1 : 0.3 },
            ]}
          >
            {publishing ? (
              <ActivityIndicator size="small" color={theme.primaryText} />
            ) : (
              <Text style={[styles.postLabel, { color: theme.primaryText }]}>
                Post
              </Text>
            )}
          </Pressable>
        </View>

        <ScrollView
          style={styles.scroll}
          contentContainerStyle={styles.scrollContent}
          keyboardShouldPersistTaps="handled"
        >
          <TextInput
            style={[styles.input, { color: theme.text }]}
            placeholder="What's new?"
            placeholderTextColor={theme.textSecondary}
            multiline
            autoFocus
            value={text}
            onChangeText={setText}
          />

          {media.length > 0 && (
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              {media.map((asset) => (
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
                    <Text style={{ color: theme.textSecondary, fontSize: 28 }}>
                      ▶
                    </Text>
                  )}
                  <Pressable
                    onPress={() => removeMedia(asset.id)}
                    style={styles.removeMedia}
                    hitSlop={8}
                  >
                    <Text style={styles.removeMediaLabel}>✕</Text>
                  </Pressable>
                </View>
              ))}
            </ScrollView>
          )}

          <Pressable onPress={pickMedia} style={styles.attach} hitSlop={8}>
            <Text style={[styles.attachLabel, { color: theme.textSecondary }]}>
              🖼️  Add photos or video
            </Text>
          </Pressable>

          <View style={[styles.divider, { backgroundColor: theme.border }]} />

          <Text style={[styles.sectionTitle, { color: theme.text }]}>
            Share to
          </Text>
          <View style={styles.chips}>
            {PLATFORMS.map((platform) => (
              <PlatformChip
                key={platform}
                platform={platform}
                selected={targets.includes(platform)}
                disabled={!connected.has(platform)}
                onToggle={toggleTarget}
              />
            ))}
          </View>
          {connected.size < PLATFORMS.length && (
            <Text style={[styles.note, { color: theme.textSecondary }]}>
              Grayed-out platforms aren't connected yet — add them in Accounts.
            </Text>
          )}

          {issues.length > 0 && (
            <View style={styles.issues}>
              {issues.map((issue, i) => (
                <Text
                  key={`${issue.platform}-${issue.code}-${i}`}
                  style={[styles.issue, { color: theme.danger }]}
                >
                  {issue.message}
                </Text>
              ))}
            </View>
          )}
        </ScrollView>

        <View style={[styles.footer, { borderTopColor: theme.border }]}>
          <Text
            style={[
              styles.counter,
              { color: remaining < 0 ? theme.danger : theme.textSecondary },
            ]}
          >
            {remaining.toLocaleString()} left · {charBudget.label} is the
            tightest
          </Text>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  cancel: { fontSize: 15 },
  headerTitle: { fontSize: 16, fontWeight: "700" },
  postButton: {
    paddingHorizontal: 18,
    paddingVertical: 8,
    borderRadius: 999,
    minWidth: 64,
    alignItems: "center",
  },
  postLabel: { fontSize: 14, fontWeight: "600" },
  scroll: { flex: 1 },
  scrollContent: { padding: 16, gap: 14 },
  input: {
    fontSize: 16,
    lineHeight: 22,
    minHeight: 96,
    textAlignVertical: "top",
  },
  media: {
    width: 120,
    height: 160,
    borderRadius: 12,
    marginRight: 8,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  removeMedia: {
    position: "absolute",
    top: 6,
    right: 6,
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: "rgba(0,0,0,0.6)",
    alignItems: "center",
    justifyContent: "center",
  },
  removeMediaLabel: { color: "#FFF", fontSize: 12 },
  attach: { paddingVertical: 4 },
  attachLabel: { fontSize: 14 },
  divider: { height: StyleSheet.hairlineWidth },
  sectionTitle: { fontSize: 15, fontWeight: "600" },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  note: { fontSize: 12, lineHeight: 17 },
  issues: { gap: 6 },
  issue: { fontSize: 13, lineHeight: 18 },
  footer: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  counter: { fontSize: 12 },
});
