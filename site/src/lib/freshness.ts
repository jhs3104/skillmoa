const DAY_MS = 86_400_000;
export const NEW_SKILL_DAYS = 7;

/** 최초 수집일에 발견된 스킬은 신규가 아니라 초기 카탈로그다 (ADR-0002). */
export function isNewSkill(firstSeenAt: string, today: string, bootstrappedOn: string | null): boolean {
  if (firstSeenAt === bootstrappedOn) return false;
  const age = (Date.parse(today) - Date.parse(firstSeenAt)) / DAY_MS;
  return age >= 0 && age < NEW_SKILL_DAYS;
}
