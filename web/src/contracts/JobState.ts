/* eslint-disable */
/**
 * GENERIERT aus schemas/JobState.schema.json (npm run gen:contracts). Nicht von Hand ändern.
 */

export interface JobState {
  message: string | null;
  progress: number;
  run_id: string | null;
  stage: string | null;
  state: "queued" | "running" | "done" | "failed" | "cancelled";
}
