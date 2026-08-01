export const FOLLOWUP_DELAY_ENABLED = true;
export const FOLLOWUP_DELAY_MIN = 20; // seconds
export const FOLLOWUP_DELAY_MAX = 30; // seconds

export async function applyFollowUpDelay() {
  if (!FOLLOWUP_DELAY_ENABLED) return;
  const delayMs = (Math.random() * (FOLLOWUP_DELAY_MAX - FOLLOWUP_DELAY_MIN) + FOLLOWUP_DELAY_MIN) * 1000;
  return new Promise(resolve => setTimeout(resolve, delayMs));
}
