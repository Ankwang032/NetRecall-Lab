import { useEffect, useState } from "react";
import { ArrowsClockwiseIcon, CardsIcon, FilePlusIcon, FlaskIcon, GraphIcon, SpinnerIcon, type Icon } from "@phosphor-icons/react";
import { BrowserRouter, NavLink, Route, Routes } from "react-router";
import { toast } from "sonner";
import { api, ApiError, errorMessage, type DueCard, type SyncResponse } from "@/api";
import { LabsPage } from "@/components/LabsPage";
import { ReviewList } from "@/components/ReviewList";
import { StudySession } from "@/components/StudySession";
import { UploadDialog } from "@/components/UploadDialog";
import { Button } from "@/components/ui/button";
import { Toaster } from "@/components/ui/sonner";
import { cn } from "@/lib/utils";

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

// 화면 경로는 설계서 §E-1. 학습 세션은 경로 없이 이 화면 안에서 연다
export function App() {
  return (
    <BrowserRouter>
      <Shell />
    </BrowserRouter>
  );
}

const NAV: { to: string; label: string; icon: Icon }[] = [
  { to: "/", label: "오늘의 복습", icon: CardsIcon },
  { to: "/labs", label: "실습", icon: FlaskIcon },
];

function Shell() {
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [session, setSession] = useState<DueCard[] | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncIssues, setSyncIssues] = useState<SyncResponse | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [topic, setTopic] = useState<string | null>(null); // 학습을 마치고 돌아와도 고른 주제를 유지한다

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

  // 고른 묶음(전체·주제·개념)을 first부터 순서대로 이어서 학습한다
  function start(pool: DueCard[], first: DueCard = pool[0]) {
    const i = pool.indexOf(first);
    setSession([...pool.slice(i), ...pool.slice(0, i)]);
  }

  function exitSession() {
    setSession(null);
    loadCards();
  }

  return (
    <div className="flex min-h-dvh">
      {/* 좁은 화면에서는 아이콘만 보인다 */}
      <aside className="sticky top-0 flex h-dvh w-16 shrink-0 flex-col gap-1.5 border-r bg-card p-2.5 md:w-68 md:p-3">
        <div className="mb-4 flex h-12 items-center gap-2.5 px-1.5 text-lg font-semibold tracking-tight">
          <span className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <GraphIcon weight="bold" className="size-5" aria-hidden />
          </span>
          <span className="hidden md:inline">NetRecall Lab</span>
        </div>
        <nav aria-label="화면" className="flex flex-col gap-1.5">
          {NAV.map(({ to, label, icon: IconComponent }) => (
            <NavLink key={to} to={to} end title={label}
              className={({ isActive }) => cn(
                "flex h-11 items-center gap-3 rounded-lg px-3 text-base font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
              )}>
              <IconComponent className="size-5 shrink-0" aria-hidden />
              <span className="hidden md:inline">{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex flex-col gap-1.5">
          <Button variant="ghost" className="h-11 justify-start gap-3 px-3 text-base [&_svg:not([class*='size-'])]:size-5" onClick={() => setUploadOpen(true)} title="개념 추가">
            <FilePlusIcon aria-hidden /> <span className="hidden md:inline">개념 추가</span>
          </Button>
          <Button variant="ghost" className="h-11 justify-start gap-3 px-3 text-base [&_svg:not([class*='size-'])]:size-5" onClick={runSync} disabled={syncing} title="동기화">
            {syncing ? <SpinnerIcon className="animate-spin" aria-hidden /> : <ArrowsClockwiseIcon aria-hidden />}
            <span className="hidden md:inline">동기화</span>
          </Button>
        </div>
      </aside>

      <main className="mx-auto w-full min-w-0 max-w-3xl px-4 py-8">
        <Routes>
          <Route
            path="/"
            element={session ? (
              <StudySession cards={session} onExit={exitSession} />
            ) : (
              <ReviewList
                cards={cards}
                topic={topic}
                onTopic={setTopic}
                error={loadError}
                syncIssues={syncIssues}
                onStart={start}
                onUpload={() => setUploadOpen(true)}
              />
            )}
          />
          <Route path="/labs" element={<LabsPage />} />
          <Route path="*" element={<p className="text-muted-foreground">없는 화면입니다.</p>} />
        </Routes>
      </main>

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} onSaved={loadCards} />
      <Toaster />
    </div>
  );
}
