import type { UserProfile } from "./api";

const KEY = "revvec:profile:v1";

export const EMPTY_PROFILE: UserProfile = {
  role: "",
  experience: "",
  focus: "",
  preferences: "",
  notes: "",
};

export function loadProfile(): UserProfile {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return { ...EMPTY_PROFILE };
    const parsed = JSON.parse(raw) as UserProfile;
    return { ...EMPTY_PROFILE, ...parsed };
  } catch {
    return { ...EMPTY_PROFILE };
  }
}

export function saveProfile(p: UserProfile): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    // localStorage full or disabled — silently ignore
  }
}

export function clearProfile(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // ignore
  }
}

/** Returns the profile only if at least one field has content; otherwise undefined. */
export function activeProfile(p: UserProfile): UserProfile | undefined {
  const trimmed: UserProfile = {};
  let any = false;
  for (const k of Object.keys(EMPTY_PROFILE) as (keyof UserProfile)[]) {
    const v = (p[k] ?? "").trim();
    if (v) {
      trimmed[k] = v;
      any = true;
    }
  }
  return any ? trimmed : undefined;
}

export function isProfileSet(p: UserProfile): boolean {
  return activeProfile(p) !== undefined;
}
