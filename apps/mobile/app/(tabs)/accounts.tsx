import { useCallback, useState } from "react";
import { useFocusEffect } from "expo-router";
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import {
  PLATFORM_CONSTRAINTS,
  type ConnectionInfo,
  type Platform,
} from "@crosspost/shared";
import { api } from "@/api";
import { PlatformIcon } from "@/components/PlatformIcon";
import { useTheme } from "@/theme";

export default function AccountsScreen() {
  const theme = useTheme();
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [busy, setBusy] = useState<Platform | null>(null);

  const load = useCallback(async () => {
    try {
      setConnections(await api.listConnections());
    } catch {
      // surfaced on the feed screen; keep this screen quiet
    }
  }, []);

  useFocusEffect(
    useCallback(() => {
      load();
    }, [load])
  );

  const toggle = async (info: ConnectionInfo) => {
    setBusy(info.platform);
    try {
      const updated = info.connected
        ? await api.disconnect(info.platform)
        : await api.connect(info.platform);
      setConnections((prev) =>
        prev.map((c) => (c.platform === updated.platform ? updated : c))
      );
    } catch (err) {
      Alert.alert(
        "Connection failed",
        err instanceof Error ? err.message : "Try again."
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: theme.background }]}
      edges={["top"]}
    >
      <View style={[styles.header, { borderBottomColor: theme.border }]}>
        <Text style={[styles.title, { color: theme.text }]}>Accounts</Text>
      </View>

      <ScrollView>
        <Text style={[styles.hint, { color: theme.textSecondary }]}>
          Connect the accounts you want CrossPost to publish to.
        </Text>

        {connections.map((info) => (
          <View
            key={info.platform}
            style={[styles.row, { borderBottomColor: theme.border }]}
          >
            <PlatformIcon platform={info.platform} size={22} color={theme.text} />
            <View style={styles.rowBody}>
              <Text style={[styles.rowTitle, { color: theme.text }]}>
                {PLATFORM_CONSTRAINTS[info.platform].label}
              </Text>
              <Text style={[styles.rowSub, { color: theme.textSecondary }]}>
                {info.connected ? info.handle ?? "Connected" : "Not connected"}
              </Text>
            </View>
            <Pressable
              onPress={() => toggle(info)}
              disabled={busy === info.platform}
              style={[
                styles.button,
                info.connected
                  ? { borderColor: theme.border, borderWidth: StyleSheet.hairlineWidth }
                  : { backgroundColor: theme.primary },
              ]}
            >
              <Text
                style={[
                  styles.buttonLabel,
                  { color: info.connected ? theme.text : theme.primaryText },
                ]}
              >
                {info.connected ? "Disconnect" : "Connect"}
              </Text>
            </Pressable>
          </View>
        ))}
      </ScrollView>
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
  hint: {
    fontSize: 13,
    lineHeight: 18,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  row: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  rowBody: { flex: 1, gap: 2 },
  rowTitle: { fontSize: 15, fontWeight: "600" },
  rowSub: { fontSize: 13 },
  button: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 999,
    minWidth: 104,
    alignItems: "center",
  },
  buttonLabel: { fontSize: 13, fontWeight: "600" },
});
