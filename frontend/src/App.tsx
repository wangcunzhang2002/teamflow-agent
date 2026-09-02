import {
  AlertCircle,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  DatabaseZap,
  ListTodo,
  Loader2,
  Play,
  RefreshCw,
  ShieldCheck,
  UserRound,
  Workflow,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";

import {
  approveActions,
  executeActions,
  extractMeeting,
  getMeeting,
  type ExecutionResult,
  type Meeting,
} from "./api";
import { Badge, Button, Card, Input, Skeleton, Textarea } from "./components/ui";

const SAMPLE_TRANSCRIPT = `[00:01] 李明：我会在周五前完成登录接口联调。
[00:18] 王珊：数据埋点方案我来负责，8月30日前发评审稿。
[00:36] 赵凯：下周一前把首页原型更新好。
[00:52] 李明：还需要有人整理试点客户名单。
[01:08] 王珊：今天先讨论到这里，下一次会议再看实验结果。`;

interface ActionDraft {
  title: string;
  owner: string;
  due_date: string;
}

const STATUS_STYLE = {
  proposed: "border-amber-200 bg-amber-50 text-amber-700",
  approved: "border-blue-200 bg-blue-50 text-blue-700",
  executed: "border-emerald-200 bg-emerald-50 text-emerald-700",
};

const STATUS_LABEL = { proposed: "待审批", approved: "已批准", executed: "已执行" };

function draftsFromMeeting(meeting: Meeting) {
  return Object.fromEntries(
    meeting.action_items.map((item) => [
      item.action_id,
      { title: item.title, owner: item.owner ?? "", due_date: item.due_date ?? "" },
    ]),
  ) as Record<string, ActionDraft>;
}

function App() {
  const [title, setTitle] = useState("产品迭代规划会");
  const [meetingDate, setMeetingDate] = useState("2026-08-26");
  const [transcript, setTranscript] = useState(SAMPLE_TRANSCRIPT);
  const [meeting, setMeeting] = useState<Meeting | null>(null);
  const [drafts, setDrafts] = useState<Record<string, ActionDraft>>({});
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [execution, setExecution] = useState<ExecutionResult | null>(null);
  const [loading, setLoading] = useState<"extract" | "approve" | "execute" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selectedComplete = useMemo(
    () =>
      [...selected].every((id) => {
        const draft = drafts[id];
        return draft && draft.title.trim() && draft.owner.trim() && draft.due_date;
      }),
    [drafts, selected],
  );

  async function handleExtract(event: FormEvent) {
    event.preventDefault();
    setLoading("extract");
    setError(null);
    setExecution(null);
    try {
      const extracted = await extractMeeting({
        title: title.trim(),
        meeting_date: meetingDate,
        transcript: transcript.trim(),
      });
      setMeeting(extracted);
      setDrafts(draftsFromMeeting(extracted));
      setSelected(
        new Set(
          extracted.action_items
            .filter((item) => item.needs_clarification.length === 0)
            .map((item) => item.action_id),
        ),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "行动项提取失败。")
    } finally {
      setLoading(null);
    }
  }

  function updateDraft(actionId: string, field: keyof ActionDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [actionId]: { ...current[actionId], [field]: value },
    }));
  }

  function toggleSelected(actionId: string) {
    setSelected((current) => {
      const next = new Set(current);
      if (next.has(actionId)) next.delete(actionId);
      else next.add(actionId);
      return next;
    });
  }

  async function handleApprove() {
    if (!meeting || selected.size === 0 || !selectedComplete) return;
    setLoading("approve");
    setError(null);
    try {
      const actionIds = [...selected];
      const approved = await approveActions(
        meeting.meeting_id,
        actionIds,
        actionIds.map((actionId) => ({
          action_id: actionId,
          title: drafts[actionId].title.trim(),
          owner: drafts[actionId].owner.trim() || null,
          due_date: drafts[actionId].due_date || null,
        })),
      );
      setMeeting(approved);
      setDrafts(draftsFromMeeting(approved));
      setSelected(new Set());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "审批失败。")
    } finally {
      setLoading(null);
    }
  }

  async function handleExecute() {
    if (!meeting) return;
    setLoading("execute");
    setError(null);
    try {
      const result = await executeActions(meeting.meeting_id);
      setExecution(result);
      const refreshed = await getMeeting(meeting.meeting_id);
      setMeeting(refreshed);
      setDrafts(draftsFromMeeting(refreshed));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "工具执行失败。")
    } finally {
      setLoading(null);
    }
  }

  const approvedCount = meeting?.action_items.filter((item) => item.status === "approved").length ?? 0;
  const executedCount = meeting?.action_items.filter((item) => item.status === "executed").length ?? 0;

  return (
    <div className="min-h-screen">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-[1540px] items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="grid size-10 place-items-center rounded-xl bg-teal-700 text-white">
              <Workflow className="size-5" aria-hidden="true" />
            </div>
            <div>
              <div className="font-semibold tracking-tight text-slate-950">TeamFlow</div>
              <div className="text-xs text-slate-500">带人工审批的项目协作同事</div>
            </div>
          </div>
          <Badge className="hidden border-teal-200 bg-teal-50 text-teal-700 sm:inline-flex">可选 LLM · Mock tools · MCP v2</Badge>
        </div>
      </header>

      <main className="mx-auto max-w-[1540px] px-4 py-8 sm:px-6 lg:px-8">
        <section className="mb-6 max-w-3xl">
          <Badge className="mb-3 border-teal-200 bg-teal-50 text-teal-700">MEETING TO EXECUTION</Badge>
          <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-4xl">
            会议结论真正进入执行系统
          </h1>
          <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-600 sm:text-base">
            Agent 提取负责人和截止日期，人修正并批准后才允许创建任务与日历提醒。所有执行都有审计记录和幂等保护。
          </p>
        </section>

        {error && (
          <Card className="mb-6 border-red-200 bg-red-50 p-4 text-sm text-red-800" aria-live="polite">
            <div className="flex items-center gap-2 font-semibold">
              <AlertCircle className="size-4" aria-hidden="true" />
              操作未完成
            </div>
            <p className="mt-1">{error}</p>
          </Card>
        )}

        <div className="grid gap-6 xl:grid-cols-[390px_minmax(0,1fr)]">
          <aside className="min-w-0 xl:sticky xl:top-6 xl:self-start">
            <Card className="overflow-hidden shadow-sm">
              <div className="border-b border-slate-200 p-5">
                <div className="flex items-center gap-2 font-semibold text-slate-900">
                  <ClipboardCheck className="size-5 text-teal-700" aria-hidden="true" />
                  会议输入
                </div>
                <p className="mt-2 text-xs leading-5 text-slate-500">支持“说话人：内容”的逐行记录，时间戳可选。</p>
              </div>
              <form onSubmit={(event) => void handleExtract(event)} className="space-y-4 p-5">
                <div>
                  <label htmlFor="meeting-title" className="mb-1.5 block text-xs font-semibold text-slate-700">
                    会议标题
                  </label>
                  <Input
                    id="meeting-title"
                    value={title}
                    onChange={(event) => setTitle(event.target.value)}
                    disabled={loading !== null}
                  />
                </div>
                <div>
                  <label htmlFor="meeting-date" className="mb-1.5 block text-xs font-semibold text-slate-700">
                    会议日期
                  </label>
                  <Input
                    id="meeting-date"
                    type="date"
                    value={meetingDate}
                    onChange={(event) => setMeetingDate(event.target.value)}
                    disabled={loading !== null}
                  />
                </div>
                <div>
                  <label htmlFor="transcript" className="mb-1.5 block text-xs font-semibold text-slate-700">
                    会议记录
                  </label>
                  <Textarea
                    id="transcript"
                    value={transcript}
                    onChange={(event) => setTranscript(event.target.value)}
                    className="min-h-72 font-mono text-xs"
                    disabled={loading !== null}
                  />
                </div>
                <Button
                  type="submit"
                  variant="primary"
                  className="w-full"
                  disabled={loading !== null || title.trim().length < 2 || transcript.trim().length < 10}
                >
                  {loading === "extract" ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                  ) : (
                    <Play className="size-4" aria-hidden="true" />
                  )}
                  {loading === "extract" ? "提取中" : meeting ? "重新提取" : "提取行动项"}
                </Button>
              </form>
            </Card>
          </aside>

          <div className="min-w-0 space-y-6">
            {loading === "extract" && !meeting ? (
              <div className="space-y-4" aria-label="正在提取行动项">
                <Skeleton className="h-24" />
                <Skeleton className="h-48" />
                <Skeleton className="h-48" />
              </div>
            ) : !meeting ? (
              <Card className="border-dashed p-8 text-center sm:p-14">
                <ListTodo className="mx-auto size-10 text-slate-400" aria-hidden="true" />
                <h2 className="mt-4 font-semibold text-slate-900">等待会议记录</h2>
                <p className="mx-auto mt-2 max-w-xl text-sm leading-6 text-slate-500">
                  点击“提取行动项”后，候选任务仍只处于 proposed 状态；在你批准前不会调用任务或日历工具。
                </p>
              </Card>
            ) : (
              <>
                <Card className="p-4 shadow-sm sm:p-5">
                  <div className="grid gap-3 sm:grid-cols-3">
                    {[
                      { label: "1. Agent 提取", done: true, detail: `${meeting.action_items.length} 个候选项` },
                      { label: "2. 人工审批", done: approvedCount + executedCount > 0, detail: `${approvedCount + executedCount} 个已批准` },
                      { label: "3. 工具执行", done: executedCount > 0, detail: `${executedCount} 个已执行` },
                    ].map((step) => (
                      <div key={step.label} className={`rounded-lg border p-3 ${step.done ? "border-emerald-200 bg-emerald-50" : "border-slate-200 bg-slate-50"}`}>
                        <div className={`flex items-center gap-2 text-sm font-semibold ${step.done ? "text-emerald-800" : "text-slate-500"}`}>
                          {step.done ? <CheckCircle2 className="size-4" aria-hidden="true" /> : <span className="size-4 rounded-full border border-slate-300" />}
                          {step.label}
                        </div>
                        <div className="mt-1 pl-6 text-xs text-slate-500">{step.detail}</div>
                      </div>
                    ))}
                  </div>
                </Card>

                <Card className="overflow-hidden shadow-sm">
                  <div className="flex flex-col justify-between gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center">
                    <div>
                      <h2 className="font-semibold text-slate-900">行动项审批台</h2>
                      <p className="mt-1 text-xs text-slate-500">勾选、修正并批准；缺负责人或截止日期时按钮保持禁用。</p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <Button
                        variant="outline"
                        onClick={() => void handleApprove()}
                        disabled={loading !== null || selected.size === 0 || !selectedComplete}
                      >
                        {loading === "approve" ? <Loader2 className="size-4 animate-spin" /> : <ShieldCheck className="size-4" />}
                        批准所选（{selected.size}）
                      </Button>
                      <Button
                        variant="primary"
                        onClick={() => void handleExecute()}
                        disabled={loading !== null || (approvedCount === 0 && executedCount === 0)}
                      >
                        {loading === "execute" ? (
                          <Loader2 className="size-4 animate-spin" aria-hidden="true" />
                        ) : executedCount > 0 && approvedCount === 0 ? (
                          <RefreshCw className="size-4" aria-hidden="true" />
                        ) : (
                          <DatabaseZap className="size-4" aria-hidden="true" />
                        )}
                        {executedCount > 0 && approvedCount === 0 ? "安全重试" : "执行已批准项"}
                      </Button>
                    </div>
                  </div>

                  <div className="divide-y divide-slate-100">
                    {meeting.action_items.map((item) => {
                      const draft = drafts[item.action_id];
                      const editable = item.status === "proposed";
                      return (
                        <article key={item.action_id} className="p-5">
                          <div className="flex items-start gap-3">
                            <input
                              type="checkbox"
                              className="mt-1 size-4 rounded border-slate-300 text-teal-700 focus:ring-teal-600"
                              checked={selected.has(item.action_id)}
                              onChange={() => toggleSelected(item.action_id)}
                              disabled={!editable || loading !== null}
                              aria-label={`选择 ${item.action_id}`}
                            />
                            <div className="min-w-0 flex-1">
                              <div className="flex flex-wrap items-center gap-2">
                                <span className="text-xs font-bold text-slate-500">{item.action_id}</span>
                                <Badge className={STATUS_STYLE[item.status]}>{STATUS_LABEL[item.status]}</Badge>
                                <span className="text-xs text-slate-400">置信度 {Math.round(item.confidence * 100)}%</span>
                              </div>
                              <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,1fr)_160px_170px]">
                                <div>
                                  <label className="mb-1 block text-[11px] font-semibold uppercase tracking-wide text-slate-500">任务内容</label>
                                  <Input
                                    value={draft?.title ?? ""}
                                    onChange={(event) => updateDraft(item.action_id, "title", event.target.value)}
                                    disabled={!editable}
                                  />
                                </div>
                                <div>
                                  <label className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    <UserRound className="size-3" /> 负责人
                                  </label>
                                  <Input
                                    value={draft?.owner ?? ""}
                                    placeholder="待人工补充"
                                    onChange={(event) => updateDraft(item.action_id, "owner", event.target.value)}
                                    disabled={!editable}
                                  />
                                </div>
                                <div>
                                  <label className="mb-1 flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                                    <CalendarDays className="size-3" /> 截止日期
                                  </label>
                                  <Input
                                    type="date"
                                    value={draft?.due_date ?? ""}
                                    onChange={(event) => updateDraft(item.action_id, "due_date", event.target.value)}
                                    disabled={!editable}
                                  />
                                </div>
                              </div>
                              {item.needs_clarification.length > 0 && editable && (
                                <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                                  <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden="true" />
                                  需人工补充：{item.needs_clarification.join("、")}
                                </div>
                              )}
                              <blockquote className="mt-3 border-l-2 border-slate-200 pl-3 text-xs leading-5 text-slate-500">
                                来源：{item.source_quote}
                              </blockquote>
                            </div>
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </Card>

                {execution && (
                  <Card className="overflow-hidden border-teal-200">
                    <div className="flex flex-col justify-between gap-3 border-b border-teal-100 bg-teal-50 p-5 sm:flex-row sm:items-center">
                      <div>
                        <h2 className="font-semibold text-teal-950">本次工具执行结果</h2>
                        <p className="mt-1 text-xs text-teal-800">
                          新建 {execution.created_count} 个；幂等拦截 {execution.duplicate_prevented_count} 个重复对象。
                        </p>
                      </div>
                      <Badge className="border-teal-200 bg-white text-teal-700">模拟外部系统</Badge>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full min-w-[640px] text-left text-sm">
                        <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-5 py-3">行动项</th>
                            <th className="px-5 py-3">工具</th>
                            <th className="px-5 py-3">外部 ID</th>
                            <th className="px-5 py-3">本次状态</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                          {execution.artifacts.map((artifact) => (
                            <tr key={artifact.artifact_id}>
                              <td className="px-5 py-3 font-medium text-slate-700">{artifact.action_id}</td>
                              <td className="px-5 py-3 text-slate-600">{artifact.tool === "task" ? "任务" : "日历"}</td>
                              <td className="px-5 py-3 font-mono text-xs text-slate-600">{artifact.external_id}</td>
                              <td className="px-5 py-3">
                                <Badge className={artifact.created ? "border-emerald-200 bg-emerald-50 text-emerald-700" : "border-blue-200 bg-blue-50 text-blue-700"}>
                                  {artifact.created ? "已创建" : "重复已拦截"}
                                </Badge>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </Card>
                )}

                <div className="grid gap-6 lg:grid-cols-2">
                  <Card className="p-5">
                    <div className="flex items-center gap-2 font-semibold text-slate-900">
                      <Workflow className="size-5 text-teal-700" aria-hidden="true" />
                      提取工作流
                    </div>
                    <ol className="mt-4 space-y-4">
                      {meeting.trace.map((step) => (
                        <li key={step.name} className="flex gap-3">
                          <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden="true" />
                          <div>
                            <div className="flex flex-wrap items-center gap-2 text-sm font-semibold text-slate-700">
                              {step.name}
                              <span className="text-[11px] font-normal tabular-nums text-slate-400">{step.duration_ms.toFixed(2)} ms</span>
                            </div>
                            <p className="mt-1 text-xs leading-5 text-slate-500">{step.summary}</p>
                          </div>
                        </li>
                      ))}
                    </ol>
                  </Card>

                  <Card className="p-5">
                    <div className="flex items-center gap-2 font-semibold text-slate-900">
                      <ShieldCheck className="size-5 text-teal-700" aria-hidden="true" />
                      审计日志
                    </div>
                    <ol className="mt-4 space-y-4">
                      {meeting.audit_log.map((event) => (
                        <li key={event.event_id} className="border-l-2 border-slate-200 pl-3">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge>{event.actor}</Badge>
                            <span className="text-xs text-slate-400">{new Date(event.occurred_at).toLocaleString("zh-CN")}</span>
                          </div>
                          <p className="mt-2 text-xs leading-5 text-slate-600">{event.detail}</p>
                        </li>
                      ))}
                    </ol>
                  </Card>
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
