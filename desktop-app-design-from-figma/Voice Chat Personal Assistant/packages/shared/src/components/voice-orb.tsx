import { motion } from "motion/react";
import simplificationSvg from "./Simplification.svg";

interface VoiceOrbProps {
  isListening: boolean;
  isProcessing: boolean;
  isSpeaking: boolean;
  size?: "sm" | "lg";
  onClick?: () => void;
}

export function LowPolyDuck() {
  const e = {
    stroke: "#00d4ff",
    strokeWidth: 2.5,
    strokeOpacity: 0.1,
    filter: "url(#edgeBlur)",
  };

  return (
    <svg
      width="100%"
      height="100%"
      viewBox="0 0 520 490"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      <defs>
        <filter id="edgeBlur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="2" />
        </filter>
        <filter id="duckGlow" x="-30%" y="-30%" width="160%" height="160%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="4" result="softBlur" />
          <feColorMatrix
            in="softBlur"
            type="matrix"
            values="0 0 0 0 0
                    0.1 0.5 0.6 0 0
                    0.1 0.6 0.8 0 0
                    0 0 0 0.35 0"
            result="coloredBlur"
          />
          <feMerge>
            <feMergeNode in="coloredBlur" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
        <filter id="eyeGlowFilter" x="-150%" y="-150%" width="400%" height="400%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="5" result="bloom" />
          <feColorMatrix
            in="bloom"
            type="matrix"
            values="1 0 0 0 0.2
                    0 1 0 0 0.3
                    0 0 1 0 0.4
                    0 0 0 0.6 0"
            result="whitenedBloom"
          />
          <feMerge>
            <feMergeNode in="whitenedBloom" />
            <feMergeNode in="SourceGraphic" />
          </feMerge>
        </filter>
      </defs>

      {/* ═══════════ HEAD — top-left, centered ~(133,130) ═══════════ */}
      <g filter="url(#duckGlow)">

      {/* Crown */}
      <polygon points="133,42 93,68 133,85" fill="#4dd0e1" {...e} />
      <polygon points="133,42 177,68 133,85" fill="#80deea" {...e} />
      <polygon points="93,68 73,60 133,42" fill="#26c6da" {...e} />
      <polygon points="177,68 200,60 133,42" fill="#4dd0e1" {...e} />

      {/* Upper head */}
      <polygon points="73,60 60,100 93,68" fill="#00acc1" {...e} />
      <polygon points="93,68 133,85 113,112" fill="#26c6da" {...e} />
      <polygon points="133,85 177,68 163,112" fill="#4dd0e1" {...e} />
      <polygon points="177,68 210,100 163,112" fill="#00bcd4" {...e} />
      <polygon points="200,60 210,100 177,68" fill="#26c6da" {...e} />
      <polygon points="73,60 93,68 60,100" fill="#0097a7" {...e} />
      <polygon points="93,68 113,112 60,100" fill="#00acc1" {...e} />
      <polygon points="133,85 163,112 113,112" fill="#80deea" {...e} />

      {/* Mid head */}
      <polygon points="60,100 65,148 113,112" fill="#00829a" {...e} />
      <polygon points="113,112 163,112 137,150" fill="#26c6da" {...e} />
      <polygon points="163,112 210,100 197,142" fill="#00acc1" {...e} />
      <polygon points="113,112 137,150 65,148" fill="#00acc1" {...e} />
      <polygon points="163,112 197,142 137,150" fill="#00bcd4" {...e} />

      {/* Lower head */}
      <polygon points="65,148 137,150 100,185" fill="#0097a7" {...e} />
      <polygon points="137,150 197,142 180,178" fill="#00acc1" {...e} />
      <polygon points="65,148 100,185 67,190" fill="#006978" {...e} />
      <polygon points="100,185 137,150 180,178" fill="#00829a" {...e} />
      <polygon points="197,142 210,100 220,135" fill="#0097a7" {...e} />

      {/* ═══════════ BEAK — pointing LEFT ═══════════ */}
      <polygon points="60,100 28,108 42,128" fill="#00838f" {...e} />
      <polygon points="28,108 5,122 22,138" fill="#006064" {...e} />
      <polygon points="60,100 42,128 60,133" fill="#00838f" {...e} />
      <polygon points="42,128 5,122 18,142" fill="#004d40" {...e} />
      <polygon points="42,128 22,138 5,122" fill="#005a4a" {...e} />
      <polygon points="60,133 42,128 18,142" fill="#004d40" {...e} />
      <polygon points="60,133 18,142 48,150" fill="#00695c" {...e} />
      <polygon points="65,148 60,133 48,150" fill="#006978" {...e} />

      {/* Mouth — dark seam across beak */}
      <line x1="8" y1="124" x2="62" y2="119" stroke="#002a33" strokeWidth="2.2" opacity="0.65" />
      <polygon points="8,124 32,128 62,119" fill="#003040" opacity="0.5" {...e} />
      <polygon points="8,124 32,128 15,134" fill="#001f28" opacity="0.4" {...e} />

      {/* ═══════════ NECK — short, head→body ═══════════ */}
      <polygon points="67,190 100,185 85,205" fill="#006978" {...e} />
      <polygon points="100,185 180,178 150,205" fill="#0097a7" {...e} />
      <polygon points="180,178 220,135 218,178" fill="#006978" {...e} />
      <polygon points="180,178 218,178 210,205" fill="#005f6e" {...e} />
      <polygon points="100,185 150,205 85,205" fill="#00829a" {...e} />
      <polygon points="180,178 210,205 150,205" fill="#00829a" {...e} />
      <polygon points="210,205 280,200 250,228" fill="#005f6e" {...e} />
      <polygon points="210,205 218,178 280,200" fill="#004d5e" {...e} />

      {/* ═══════════ BODY — plump, centered ~(285,310) ═══════════ */}

      {/* Shoulder */}
      <polygon points="85,205 150,205 125,228" fill="#006978" {...e} />
      <polygon points="150,205 210,205 185,228" fill="#0097a7" {...e} />
      <polygon points="185,228 150,205 125,228" fill="#00829a" {...e} />
      <polygon points="210,205 250,228 185,228" fill="#0097a7" {...e} />
      <polygon points="85,205 125,228 68,232" fill="#005f6e" {...e} />
      <polygon points="280,200 375,218 250,228" fill="#005f6e" {...e} />
      <polygon points="280,200 375,218 360,202" fill="#004d5e" {...e} />

      {/* Upper body */}
      <polygon points="68,232 125,228 108,275" fill="#005261" {...e} />
      <polygon points="125,228 185,228 160,275" fill="#00acc1" {...e} />
      <polygon points="185,228 250,228 220,275" fill="#00829a" {...e} />
      <polygon points="250,228 375,218 325,270" fill="#0097a7" {...e} />
      <polygon points="125,228 160,275 108,275" fill="#00829a" {...e} />
      <polygon points="185,228 220,275 160,275" fill="#00acc1" {...e} />
      <polygon points="250,228 325,270 220,275" fill="#00829a" {...e} />
      <polygon points="68,232 108,275 42,278" fill="#004d5e" {...e} />
      <polygon points="375,218 438,270 325,270" fill="#004d5e" {...e} />

      {/* Mid body — widest */}
      <polygon points="42,278 108,275 80,328" fill="#004d5e" {...e} />
      <polygon points="108,275 160,275 138,328" fill="#00acc1" {...e} />
      <polygon points="160,275 220,275 192,328" fill="#0097a7" {...e} />
      <polygon points="220,275 325,270 278,325" fill="#0097a7" {...e} />
      <polygon points="325,270 438,270 390,322" fill="#005261" {...e} />
      <polygon points="108,275 138,328 80,328" fill="#006978" {...e} />
      <polygon points="160,275 192,328 138,328" fill="#00829a" {...e} />
      <polygon points="220,275 278,325 192,328" fill="#00829a" {...e} />
      <polygon points="325,270 390,322 278,325" fill="#006978" {...e} />
      <polygon points="42,278 80,328 28,323" fill="#003845" {...e} />
      <polygon points="438,270 455,318 390,322" fill="#003845" {...e} />

      {/* Lower body */}
      <polygon points="28,323 80,328 58,373" fill="#003845" {...e} />
      <polygon points="80,328 138,328 118,373" fill="#005f6e" {...e} />
      <polygon points="138,328 192,328 168,373" fill="#006978" {...e} />
      <polygon points="192,328 278,325 240,371" fill="#00829a" {...e} />
      <polygon points="278,325 390,322 342,370" fill="#005f6e" {...e} />
      <polygon points="390,322 455,318 428,368" fill="#003845" {...e} />
      <polygon points="80,328 118,373 58,373" fill="#004d5e" {...e} />
      <polygon points="138,328 168,373 118,373" fill="#005f6e" {...e} />
      <polygon points="192,328 240,371 168,373" fill="#006978" {...e} />
      <polygon points="278,325 342,370 240,371" fill="#006978" {...e} />
      <polygon points="390,322 428,368 342,370" fill="#004d5e" {...e} />

      {/* Bottom body */}
      <polygon points="58,373 118,373 92,405" fill="#002a33" {...e} />
      <polygon points="118,373 168,373 148,405" fill="#003845" {...e} />
      <polygon points="168,373 240,371 208,403" fill="#005261" {...e} />
      <polygon points="240,371 342,370 295,403" fill="#005261" {...e} />
      <polygon points="342,370 428,368 392,402" fill="#002a33" {...e} />
      <polygon points="118,373 148,405 92,405" fill="#003845" {...e} />
      <polygon points="168,373 208,403 148,405" fill="#004d5e" {...e} />
      <polygon points="240,371 295,403 208,403" fill="#004d5e" {...e} />
      <polygon points="342,370 392,402 295,403" fill="#003845" {...e} />

      {/* Flat bottom */}
      <polygon points="92,405 148,405 125,425" fill="#001f28" {...e} />
      <polygon points="148,405 208,403 180,425" fill="#002a33" {...e} />
      <polygon points="208,403 295,403 252,427" fill="#003040" {...e} />
      <polygon points="295,403 392,402 348,425" fill="#001f28" {...e} />
      <polygon points="125,425 180,425 148,405" fill="#001a22" {...e} />
      <polygon points="180,425 252,427 208,403" fill="#002028" {...e} />
      <polygon points="252,427 348,425 295,403" fill="#002028" {...e} />

      {/* ═══════════ WING ═══════════ */}
      <polygon points="148,258 310,254 240,308" fill="#0097a7" opacity="0.45" {...e} />
      <polygon points="148,258 240,308 138,302" fill="#00829a" opacity="0.4" {...e} />
      <polygon points="310,254 375,295 240,308" fill="#006978" opacity="0.4" {...e} />

      </g>

      {/* ═══════════ EYE — cyborg white glow ═══════════ */}
      <g filter="url(#eyeGlowFilter)">
        <circle cx="100" cy="108" r="14" fill="#00d4ff" opacity="0.25" />
        <circle cx="100" cy="108" r="11" fill="#e0f7fa" opacity="0.4" />
        <circle cx="100" cy="108" r="8.5" fill="#e8f4ff" />
        <circle cx="100" cy="108" r="7" fill="url(#eyeGlow)" />
        <circle cx="100" cy="108" r="4.5" fill="#ffffff" />
        <circle cx="98" cy="106" r="2" fill="#ffffff" opacity="0.95" />
        <circle cx="103" cy="111" r="1" fill="#e0f7fa" opacity="0.5" />
      </g>

      {/* ═══════════ HIGHLIGHT EDGES ═══════════ */}
      <line x1="133" y1="42" x2="177" y2="68" stroke="#b2ebf2" strokeWidth="0.8" opacity="0.18" />
      <line x1="133" y1="42" x2="93" y2="68" stroke="#b2ebf2" strokeWidth="0.8" opacity="0.18" />
      <line x1="133" y1="85" x2="163" y2="112" stroke="#b2ebf2" strokeWidth="0.5" opacity="0.12" />
      <line x1="215" y1="275" x2="278" y2="325" stroke="#b2ebf2" strokeWidth="0.4" opacity="0.08" />
    </svg>
  );
}

export function VoiceOrb({
  isListening,
  isProcessing,
  isSpeaking,
  size = "sm",
  onClick,
}: VoiceOrbProps) {
  const active = isListening || isProcessing || isSpeaking;
  const isLarge = size === "lg";

  const getAccentColor = () => {
    if (isListening) return "#00d4ff";
    if (isProcessing) return "#7b61ff";
    if (isSpeaking) return "#00ffa3";
    return "#00d4ff";
  };

  const accent = getAccentColor();

  const containerSize = isLarge
    ? "w-80 h-80 md:w-[24rem] md:h-[26rem]"
    : "w-52 h-56";

  const duckSize = isLarge
    ? "w-72 h-68 md:w-[20rem] md:h-[18rem]"
    : "w-44 h-40";

  return (
    <motion.button
      className={`relative flex flex-col items-center justify-center ${containerSize} cursor-pointer`}
      onClick={onClick}
      disabled={active}
      whileTap={!active ? { scale: 0.95 } : undefined}
      whileHover={!active ? { scale: 1.03 } : undefined}
    >
      {/* Ambient glow — only animates when active */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: "75%",
          height: "55%",
          background: `radial-gradient(circle, ${accent}1a 0%, ${accent}08 50%, transparent 75%)`,
        }}
        animate={
          active
            ? { scale: [1, 1.3, 1], opacity: [0.5, 0.9, 0.5] }
            : { scale: 1, opacity: 0.3 }
        }
        transition={
          active
            ? { duration: 1.5, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.6, ease: "easeOut" }
        }
      />

      {/* Pulse rings */}
      {active && (
        <>
          <motion.div
            className="absolute rounded-full"
            style={{ border: `1.5px solid ${accent}` }}
            animate={{
              width: isLarge ? [200, 360] : [130, 220],
              height: isLarge ? [200, 360] : [130, 220],
              opacity: [0.4, 0],
            }}
            transition={{ duration: 2, repeat: Infinity, ease: "easeOut" }}
          />
          <motion.div
            className="absolute rounded-full"
            style={{ border: `1px solid ${accent}` }}
            animate={{
              width: isLarge ? [200, 310] : [130, 190],
              height: isLarge ? [200, 310] : [130, 190],
              opacity: [0.25, 0],
            }}
            transition={{
              duration: 2,
              repeat: Infinity,
              ease: "easeOut",
              delay: 0.5,
            }}
          />
        </>
      )}

      {/* Duck image — static when idle */}
      <motion.div
        className={`relative ${duckSize}`}
        style={{
          filter: `drop-shadow(0 0 ${isLarge ? 30 : 16}px ${accent}45) drop-shadow(0 0 ${isLarge ? 60 : 30}px ${accent}15)`,
        }}
        animate={
          active
            ? { scale: [1, 1.045, 1], y: [0, -5, 0] }
            : { scale: 1, y: 0 }
        }
        transition={
          active
            ? { duration: 1.5, repeat: Infinity, ease: "easeInOut" }
            : { duration: 0.6, ease: "easeOut" }
        }
      >
        <img src={simplificationSvg} alt="DuckyAI" className="w-full h-full" />
      </motion.div>

      {/* DuckAI label */}
      <motion.div
        className="flex flex-col items-center gap-0.5 mt-3"
        animate={active ? { opacity: [0.8, 1, 0.8] } : {}}
        transition={{ duration: 2, repeat: Infinity, ease: "easeInOut" }}
      >
        <span
          className="select-none"
          style={{
            color: "#e0e6f0",
            fontSize: isLarge ? "1.35rem" : "0.8rem",
            fontFamily:
              "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
            letterSpacing: "0.25em",
            opacity: 0.9,
          }}
        >
          DuckAI
        </span>
        <span
          className="select-none"
          style={{
            color: active ? accent : "#6b7fa3",
            fontSize: isLarge ? "0.55rem" : "0.45rem",
            fontFamily:
              "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
            letterSpacing: "0.3em",
            opacity: 0.55,
          }}
        >
          {isListening
            ? "LISTENING"
            : isProcessing
              ? "PROCESSING"
              : isSpeaking
                ? "SPEAKING"
                : "TAP TO SPEAK"}
        </span>
      </motion.div>
    </motion.button>
  );
}