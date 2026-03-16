import { useMemo } from "react";
import { DebaterConfig } from "../types";

/**
 * Professional avatar component.
 * Priority: avatar_url (backend AI-generated) → gradient initials fallback.
 * No cartoon avatars — clean, modern, serious aesthetic.
 */

// Deterministic palette — earthy, muted, professional tones
const GRADIENT_PAIRS = [
  ["#2c3e50", "#34495e"], // charcoal
  ["#1a2a3a", "#2d4a5e"], // deep navy
  ["#3b3a30", "#5c5b50"], // warm graphite
  ["#2d3436", "#636e72"], // slate
  ["#1e272e", "#485460"], // dark steel
  ["#4a3728", "#6b5344"], // mahogany
  ["#2c2c54", "#474787"], // ink violet
  ["#3d3d3d", "#5a5a5a"], // carbon
];

function hashString(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = (hash << 5) - hash + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function getInitials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  // For CJK single-word names, take first 1-2 chars
  const firstChar = name.trim().charAt(0);
  if (/[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]/.test(firstChar)) {
    return name.trim().slice(0, 2);
  }
  return name.trim().slice(0, 2).toUpperCase();
}

interface AvatarProps {
  debater: DebaterConfig;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}

const SIZE_MAP = {
  sm: { container: "w-10 h-10", text: "text-xs", emoji: "text-[8px]" },
  md: { container: "w-16 h-16", text: "text-lg", emoji: "text-[10px]" },
  lg: { container: "w-48 h-48", text: "text-5xl", emoji: "text-base" },
  xl: { container: "w-64 h-64", text: "text-6xl", emoji: "text-lg" },
};

export default function Avatar({ debater, size = "md", className = "" }: AvatarProps) {
  const sizeStyle = SIZE_MAP[size];

  const gradientStyle = useMemo(() => {
    const idx = hashString(debater.name) % GRADIENT_PAIRS.length;
    const [from, to] = GRADIENT_PAIRS[idx];
    return {
      background: `linear-gradient(135deg, ${from} 0%, ${to} 100%)`,
    };
  }, [debater.name]);

  const initials = useMemo(() => getInitials(debater.name), [debater.name]);

  // If backend provided a real avatar_url, use it
  if (debater.avatar_url) {
    return (
      <div
        className={`${sizeStyle.container} rounded-full overflow-hidden flex-shrink-0 ${className}`}
      >
        <img
          src={debater.avatar_url}
          alt={debater.name}
          className="w-full h-full object-cover"
          onError={(e) => {
            // Fallback to initials if image fails
            const target = e.currentTarget;
            target.style.display = "none";
            const parent = target.parentElement;
            if (parent) {
              Object.assign(parent.style, gradientStyle);
              parent.innerHTML = `<span class="w-full h-full flex items-center justify-center ${sizeStyle.text} font-bold text-white/90 select-none">${initials}</span>`;
            }
          }}
        />
      </div>
    );
  }

  // Gradient + initials fallback — clean, professional
  return (
    <div
      className={`${sizeStyle.container} rounded-full overflow-hidden flex-shrink-0 relative ${className}`}
      style={gradientStyle}
    >
      <div className="absolute inset-0 flex items-center justify-center">
        <span
          className={`${sizeStyle.text} font-bold text-white/90 select-none`}
          style={{ letterSpacing: "0.05em" }}
        >
          {initials}
        </span>
      </div>
      {/* Subtle inner shadow for depth */}
      <div className="absolute inset-0 rounded-full shadow-[inset_0_2px_8px_rgba(0,0,0,0.2)]" />
    </div>
  );
}

/**
 * Standalone helper for places that just need a URL-like src.
 * Returns null if no avatar_url — callers should handle fallback.
 */
export function getAvatarUrl(debater: DebaterConfig): string | null {
  return debater.avatar_url || null;
}
