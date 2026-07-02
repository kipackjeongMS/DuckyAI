import { Pressable, StyleSheet, Text } from "react-native";
import { PLATFORM_CONSTRAINTS, type Platform } from "@crosspost/shared";
import { useTheme } from "@/theme";
import { PlatformIcon } from "./PlatformIcon";

/**
 * Toggleable pill for selecting a target platform in the composer.
 * Selected: solid (black/white); unselected: hairline outline.
 */
export function PlatformChip({
  platform,
  selected,
  disabled,
  onToggle,
}: {
  platform: Platform;
  selected: boolean;
  disabled?: boolean;
  onToggle: (platform: Platform) => void;
}) {
  const theme = useTheme();
  const fg = selected ? theme.primaryText : theme.text;

  return (
    <Pressable
      onPress={() => onToggle(platform)}
      disabled={disabled}
      style={[
        styles.chip,
        {
          backgroundColor: selected ? theme.primary : "transparent",
          borderColor: theme.border,
          opacity: disabled ? 0.35 : 1,
        },
      ]}
    >
      <PlatformIcon platform={platform} size={14} color={fg} />
      <Text style={[styles.label, { color: fg }]}>
        {PLATFORM_CONSTRAINTS[platform].label}
      </Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chip: {
    flexDirection: "row",
    alignItems: "center",
    gap: 6,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: StyleSheet.hairlineWidth,
  },
  label: {
    fontSize: 13,
    fontWeight: "600",
  },
});
