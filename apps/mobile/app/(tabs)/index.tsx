import { useCallback, useState } from "react";
import { useFocusEffect, useRouter } from "expo-router";
import {
  FlatList,
  Pressable,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import type { UniversalPost } from "@crosspost/shared";
import { api } from "@/api";
import { PostCard } from "@/components/PostCard";
import { useTheme } from "@/theme";

export default function FeedScreen() {
  const theme = useTheme();
  const router = useRouter();
  const [posts, setPosts] = useState<UniversalPost[]>([]);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setPosts(await api.listPosts());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reach the server");
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  }, [load]);

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: theme.background }]}
      edges={["top"]}
    >
      <View style={[styles.header, { borderBottomColor: theme.border }]}>
        <Text style={[styles.title, { color: theme.text }]}>CrossPost</Text>
      </View>

      {error ? (
        <View style={styles.empty}>
          <Text style={[styles.emptyTitle, { color: theme.text }]}>
            Can't reach the server
          </Text>
          <Text style={[styles.emptyBody, { color: theme.textSecondary }]}>
            {error}
          </Text>
        </View>
      ) : (
        <FlatList
          data={posts}
          keyExtractor={(p) => p.id}
          renderItem={({ item }) => <PostCard post={item} />}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} />
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={[styles.emptyTitle, { color: theme.text }]}>
                Nothing here yet
              </Text>
              <Text style={[styles.emptyBody, { color: theme.textSecondary }]}>
                Write a post once and publish it to Instagram, Facebook,
                Threads, X and TikTok at the same time.
              </Text>
              <Pressable
                onPress={() => router.push("/compose")}
                style={[styles.cta, { backgroundColor: theme.primary }]}
              >
                <Text style={[styles.ctaLabel, { color: theme.primaryText }]}>
                  Write your first post
                </Text>
              </Pressable>
            </View>
          }
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  title: { fontSize: 24, fontWeight: "700", letterSpacing: -0.5 },
  empty: {
    alignItems: "center",
    gap: 10,
    paddingHorizontal: 32,
    paddingTop: 120,
  },
  emptyTitle: { fontSize: 17, fontWeight: "600" },
  emptyBody: { fontSize: 14, lineHeight: 20, textAlign: "center" },
  cta: {
    marginTop: 8,
    paddingHorizontal: 20,
    paddingVertical: 12,
    borderRadius: 999,
  },
  ctaLabel: { fontSize: 14, fontWeight: "600" },
});
