import { useEffect, useState } from "react";
import { ArrowsClockwiseIcon, FilePlusIcon, GraphIcon, SpinnerIcon } from "@phosphor-icons/react";
import { toast } from "sonner";
import { api, ApiError, errorMessage, type DueCard, type SyncResponse } from "@/api";
import { ReviewList } from "@/components/ReviewList";
import { StudySession } from "@/components/StudySession";
import { UploadDialog } from "@/components/UploadDialog";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";

const SYNC_LABELS: Record<string, string> = {
  created: "새로 추가",
  updated: "수정",
  relocated: "이동",
  restored: "복구",
  taken_over: "넘겨받음",
  archived: "보관",
  unchanged: "변경 없음",
  kept_due_to_error: "오류로 이전 상태 유지",
};

function summarize(summary: Record<string, number>) {
  const parts = Object.entries(SYNC_LABELS)
    .filter(([key]) => summary[key] > 0)
    .map(([key, label]) => `${label} ${summary[key]}`);
  return parts.length > 0 ? parts.join(" · ") : "개념 없음";
}

// Notion 항목의 source_ref는 페이지 id라 보여 주지 않고 "Notion"으로 바꾼다 (메시지 앞에 행 이름이 있다)
function mergeIssues(markdown: SyncResponse, notion: SyncResponse | null): SyncResponse {
  const label = (items: SyncResponse["errors"]) => items.map((i) => ({ ...i, source_ref: "Notion" }));
  return {
    ...markdown,
    errors: [...markdown.errors, ...label(notion?.errors ?? [])],
    warnings: [...markdown.warnings, ...label(notion?.warnings ?? [])],
    dangling_refs: [...markdown.dangling_refs, ...(notion?.dangling_refs ?? [])],
  };
}

export function App() {
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [session, setSession] = useState<DueCard[] | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncIssues, setSyncIssues] = useState<SyncResponse | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);

  async function loadCards() {
    try {
      setCards(await api.dueCards());
      setLoadError(null);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadCards();
  }, []);

  // Markdown 폴더를 동기화하고, Notion 데이터베이스가 설정되어 있으면(503이 아니면) 이어서 동기화한다
  async function runSync() {
    setSyncing(true);
    try {
      const markdown = await api.sync();
      let notion: SyncResponse | null = null;
      try {
        notion = await api.syncNotion();
      } catch (e) {
        if (!(e instanceof ApiError && e.status === 503)) {
          toast.error("Notion을 동기화하지 못했습니다", { description: errorMessage(e) });
        }
      }
      const issues = mergeIssues(markdown, notion);
      setSyncIssues(issues.errors.length + issues.warnings.length + issues.dangling_refs.length > 0 ? issues : null);
      toast.success("동기화했습니다", {
        description: notion
          ? `Markdown ${summarize(markdown.summary)} / Notion ${summarize(notion.summary)}`
          : summarize(markdown.summary),
      });
      await loadCards();
    } catch (e) {
      toast.error("동기화하지 못했습니다", { description: errorMessage(e) });
    } finally {
      setSyncing(false);
    }
  }

  // 고른 카드부터 목록 순서대로 이어서 학습한다
  function start(card: DueCard) {
    if (!cards) return;
    const i = cards.indexOf(card);
    setSession([...cards.slice(i), ...cards.slice(0, i)]);
  }

  function exitSession() {
    setSession(null);
    loadCards();
  }

  return (
    <div className="min-h-dvh">
      <header className="sticky top-0 z-10 border-b bg-background/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-3xl items-center gap-2 px-4">
          <div className="flex items-center gap-2 font-semibold tracking-tight">
            <span className="flex size-7 items-center justify-center rounded-md bg-primary text-primary-foreground">
              <GraphIcon weight="bold" className="size-4" aria-hidden />
            </span>
            NetRecall Lab
          </div>
          <div className="ml-auto flex items-center gap-1.5">
            <Button variant="outline" onClick={() => setUploadOpen(true)}>
              <FilePlusIcon aria-hidden /> 개념 추가
            </Button>
            <Button variant="ghost" onClick={runSync} disabled={syncing}>
              {syncing ? <SpinnerIcon className="animate-spin" aria-hidden /> : <ArrowsClockwiseIcon aria-hidden />}
              동기화
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8">
        {session ? (
          <StudySession cards={session} onExit={exitSession} />
        ) : (
          <ReviewList
            cards={cards}
            error={loadError}
            syncIssues={syncIssues}
            onStart={start}
            onUpload={() => setUploadOpen(true)}
          />
        )}
      </main>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} onSaved={loadCards} />
      <Toaster />
    </div>
  );
}
