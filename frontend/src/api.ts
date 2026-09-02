export interface ActionItem {
  action_id: string;
  title: string;
  owner: string | null;
  due_date: string | null;
  source_quote: string;
  confidence: number;
  needs_clarification: string[];
  status: "proposed" | "approved" | "executed";
}

export interface Meeting {
  meeting_id: string;
  title: string;
  meeting_date: string;
  transcript: string;
  action_items: ActionItem[];
  trace: Array<{ name: string; summary: string; duration_ms: number }>;
  audit_log: Array<{
    event_id: string;
    event_type: "extracted" | "approved" | "executed";
    actor: "agent" | "human" | "tool";
    detail: string;
    occurred_at: string;
  }>;
  metrics: Record<string, number>;
}

export interface ExecutionResult {
  meeting_id: string;
  artifacts: Array<{
    artifact_id: string;
    action_id: string;
    tool: "task" | "calendar";
    external_id: string;
    payload: Record<string, unknown>;
    created: boolean;
  }>;
  created_count: number;
  duplicate_prevented_count: number;
}

async function parseError(response: Response) {
  const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
  return payload?.detail ?? `请求失败（HTTP ${response.status}）`;
}

export async function extractMeeting(input: {
  title: string;
  meeting_date: string;
  transcript: string;
}): Promise<Meeting> {
  const response = await fetch("/api/meetings/extract", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as Meeting;
}

export async function approveActions(
  meetingId: string,
  actionIds: string[],
  edits: Array<{ action_id: string; title: string; owner: string | null; due_date: string | null }>,
): Promise<Meeting> {
  const response = await fetch(`/api/meetings/${meetingId}/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action_ids: actionIds, edits }),
  });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as Meeting;
}

export async function executeActions(meetingId: string): Promise<ExecutionResult> {
  const response = await fetch(`/api/meetings/${meetingId}/execute`, { method: "POST" });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as ExecutionResult;
}

export async function getMeeting(meetingId: string): Promise<Meeting> {
  const response = await fetch(`/api/meetings/${meetingId}`);
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as Meeting;
}
