import { useColorScheme } from "react-native";

/**
 * Threads-inspired design tokens: near-monochrome, hairline borders,
 * generous whitespace, a single black (or white, in dark mode) pill CTA.
 */
export interface Theme {
  background: string;
  card: string;
  text: string;
  textSecondary: string;
  border: string;
  primary: string;
  primaryText: string;
  danger: string;
  success: string;
}

export const lightTheme: Theme = {
  background: "#FFFFFF",
  card: "#FFFFFF",
  text: "#000000",
  textSecondary: "#999999",
  border: "#E8E8E8",
  primary: "#000000",
  primaryText: "#FFFFFF",
  danger: "#FF3040",
  success: "#00A040",
};

export const darkTheme: Theme = {
  background: "#101010",
  card: "#181818",
  text: "#F3F5F7",
  textSecondary: "#777777",
  border: "#2A2A2A",
  primary: "#FFFFFF",
  primaryText: "#000000",
  danger: "#FF3040",
  success: "#00C853",
};

export function useTheme(): Theme {
  return useColorScheme() === "dark" ? darkTheme : lightTheme;
}
