import { useState } from "react";
import { motion } from "motion/react";
import { Eye, EyeOff, ArrowRight } from "lucide-react";
import { LowPolyDuck } from "./voice-orb";

interface LoginScreenProps {
  onLogin: () => void;
}

export function LoginScreen({ onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setTimeout(() => {
      setIsLoading(false);
      onLogin();
    }, 1500);
  };

  return (
    <div
      className="h-screen w-screen flex items-center justify-center overflow-hidden relative"
      style={{
        background: "#0a0e1a",
        fontFamily: "'Inter', system-ui, sans-serif",
      }}
    >
      {/* Background radial glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 50% 35%, rgba(0,212,255,0.06) 0%, transparent 55%)",
        }}
      />

      {/* Subtle grid overlay */}
      <div
        className="absolute inset-0 pointer-events-none opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(0,212,255,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(0,212,255,0.3) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
        }}
      />

      {/* Floating particles */}
      {[...Array(6)].map((_, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{
            width: 2 + Math.random() * 3,
            height: 2 + Math.random() * 3,
            background: "#00d4ff",
            left: `${15 + Math.random() * 70}%`,
            top: `${10 + Math.random() * 80}%`,
          }}
          animate={{
            y: [0, -30 - Math.random() * 20, 0],
            opacity: [0.1, 0.4, 0.1],
          }}
          transition={{
            duration: 4 + Math.random() * 3,
            repeat: Infinity,
            ease: "easeInOut",
            delay: Math.random() * 3,
          }}
        />
      ))}

      <motion.div
        className="relative z-10 flex flex-col items-center w-full max-w-sm mx-4"
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: "easeOut" }}
      >
        {/* Duck with ambient glow */}
        <motion.div
          className="relative w-40 h-36 md:w-48 md:h-44 mb-2"
          style={{
            filter:
              "drop-shadow(0 0 24px rgba(0,212,255,0.3)) drop-shadow(0 0 50px rgba(0,212,255,0.1))",
          }}
          animate={{
            y: [0, -4, 0],
          }}
          transition={{
            duration: 4,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        >
          <LowPolyDuck />
        </motion.div>

        {/* Title */}
        <motion.div
          className="flex flex-col items-center mb-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3, duration: 0.6 }}
        >
          <h1
            className="text-foreground"
            style={{
              fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
              fontSize: "1.6rem",
              letterSpacing: "0.3em",
              color: "#e0e6f0",
            }}
          >
            DUCKAI
          </h1>
          <p
            style={{
              fontSize: "0.65rem",
              letterSpacing: "0.15em",
              color: "#6b7fa3",
              marginTop: "4px",
            }}
          >
            AUTHENTICATE TO CONTINUE
          </p>
        </motion.div>

        {/* Login form */}
        <motion.form
          className="w-full flex flex-col gap-4"
          onSubmit={handleSubmit}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.5, duration: 0.6 }}
        >
          {/* Email field */}
          <div className="flex flex-col gap-1.5">
            <label
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.12em",
                color: "#6b7fa3",
                textTransform: "uppercase",
              }}
            >
              Identifier
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-4 py-3 rounded-lg outline-none transition-all"
              style={{
                background: "rgba(26,35,50,0.6)",
                border: "1px solid rgba(0,212,255,0.1)",
                color: "#e0e6f0",
                fontSize: "0.85rem",
              }}
              onFocus={(e) =>
                (e.target.style.borderColor = "rgba(0,212,255,0.35)")
              }
              onBlur={(e) =>
                (e.target.style.borderColor = "rgba(0,212,255,0.1)")
              }
            />
          </div>

          {/* Password field */}
          <div className="flex flex-col gap-1.5">
            <label
              style={{
                fontSize: "0.65rem",
                letterSpacing: "0.12em",
                color: "#6b7fa3",
                textTransform: "uppercase",
              }}
            >
              Passkey
            </label>
            <div className="relative">
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter your passkey"
                className="w-full px-4 py-3 pr-11 rounded-lg outline-none transition-all"
                style={{
                  background: "rgba(26,35,50,0.6)",
                  border: "1px solid rgba(0,212,255,0.1)",
                  color: "#e0e6f0",
                  fontSize: "0.85rem",
                }}
                onFocus={(e) =>
                  (e.target.style.borderColor = "rgba(0,212,255,0.35)")
                }
                onBlur={(e) =>
                  (e.target.style.borderColor = "rgba(0,212,255,0.1)")
                }
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 p-1"
                style={{ color: "#6b7fa3" }}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          {/* Remember + Forgot */}
          <div className="flex items-center justify-between">
            <label className="flex items-center gap-2 cursor-pointer">
              <div
                className="w-3.5 h-3.5 rounded-sm border flex items-center justify-center"
                style={{ borderColor: "rgba(0,212,255,0.2)" }}
              >
                <div
                  className="w-1.5 h-1.5 rounded-[1px]"
                  style={{ background: "#00d4ff", opacity: 0 }}
                />
              </div>
              <span style={{ fontSize: "0.7rem", color: "#6b7fa3" }}>
                Stay authenticated
              </span>
            </label>
            <button
              type="button"
              style={{ fontSize: "0.7rem", color: "#00d4ff", opacity: 0.7 }}
              className="hover:opacity-100 transition-opacity"
            >
              Reset passkey
            </button>
          </div>

          {/* Submit button */}
          <motion.button
            type="submit"
            disabled={isLoading}
            className="w-full py-3 rounded-lg flex items-center justify-center gap-2 mt-2 cursor-pointer transition-all"
            style={{
              background: isLoading
                ? "rgba(0,212,255,0.15)"
                : "rgba(0,212,255,0.12)",
              border: "1px solid rgba(0,212,255,0.25)",
              color: "#00d4ff",
              fontSize: "0.8rem",
              letterSpacing: "0.15em",
            }}
            whileHover={
              !isLoading
                ? {
                    backgroundColor: "rgba(0,212,255,0.2)",
                    borderColor: "rgba(0,212,255,0.4)",
                  }
                : undefined
            }
            whileTap={!isLoading ? { scale: 0.98 } : undefined}
          >
            {isLoading ? (
              <motion.div
                className="w-4 h-4 rounded-full"
                style={{ border: "2px solid rgba(0,212,255,0.3)", borderTopColor: "#00d4ff" }}
                animate={{ rotate: 360 }}
                transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
              />
            ) : (
              <>
                INITIALIZE SESSION
                <ArrowRight size={15} />
              </>
            )}
          </motion.button>
        </motion.form>

        {/* Divider */}
        <div className="flex items-center gap-3 w-full mt-6 mb-4">
          <div
            className="flex-1 h-px"
            style={{ background: "rgba(0,212,255,0.08)" }}
          />
          <span style={{ fontSize: "0.6rem", color: "#4a5a78", letterSpacing: "0.1em" }}>
            OR
          </span>
          <div
            className="flex-1 h-px"
            style={{ background: "rgba(0,212,255,0.08)" }}
          />
        </div>

        {/* SSO button */}
        <motion.button
          className="w-full py-2.5 rounded-lg flex items-center justify-center gap-2 cursor-pointer transition-all"
          style={{
            background: "transparent",
            border: "1px solid rgba(0,212,255,0.1)",
            color: "#6b7fa3",
            fontSize: "0.75rem",
            letterSpacing: "0.08em",
          }}
          whileHover={{
            borderColor: "rgba(0,212,255,0.25)",
            color: "#e0e6f0",
          }}
        >
          Continue with SSO
        </motion.button>

        {/* Footer */}
        <motion.p
          className="mt-8 text-center"
          style={{ fontSize: "0.6rem", color: "#3a4a66", letterSpacing: "0.05em" }}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.8, duration: 0.6 }}
        >
          DuckAI v3.2.1 &middot; Secure Connection &middot; Encrypted
        </motion.p>
      </motion.div>
    </div>
  );
}
