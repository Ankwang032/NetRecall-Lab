import { useEffect, useState } from "react";
import { api, errorMessage, type DueCard, type ReviewResult, type SyncResponse } from "./api";
import { Study } from "./Study";

const SYNC_LABELS: Record<string, string> = {
  created: "새로 추가",
  updated: "수정",
  relocated: "이동",
  restored: "복구",
  archived: "보관",
  unchanged: "변경 없음",
  kept_due_to_error: "오류로 이전 상태 유지",
};

function formatKst(iso: string) {
  return new Date(iso).toLocaleString("ko-KR", {
    timeZone: "Asia/Seoul",
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function App() {
  const [cards, setCards] = useState<DueCard[] | null>(null);
  const [selected, setSelected] = useState<DueCard | null>(null);
  const [sync, setSync] = useState<SyncResponse | null>(null);
  const [lastReview, setLastReview] = useState<ReviewResult | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadCards() {
    try {
      setCards(await api.dueCards());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadCards();
  }, []);

  async function runSync() {
    setSyncing(true);
    setError(null);
    setLastReview(null);
    try {
      setSync(await api.sync());
      await loadCards();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSyncing(false);
    }
  }

  function select(card: DueCard) {
    setError(null);
    setSync(null);
    setLastReview(null);
    setSelected(card);
  }

  function finish(result: ReviewResult) {
    setLastReview(result);
    setSelected(null);
    loadCards();
  }

  return (
    <main>
      <header>
        <h1>NetRecall Lab</h1>
        {!selected && (
          <button onClick={runSync} disabled={syncing}>
            {syncing ? "동기화 중…" : "개념 동기화"}
          </button>
        )}
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      {selected ? (
        <Study card={selected} onDone={finish} onCancel={() => setSelected(null)} />
      ) : (
        <>
          {sync && <SyncReport result={sync} />}
          {lastReview && <p className="notice">다음 복습: {formatKst(lastReview.next_due_at)}</p>}
          {cards === null ? (
            !error && <p className="muted">불러오는 중…</p>
          ) : (
            <DueList cards={cards} onSelect={select} />
          )}
        </>
      )}
    </main>
  );
}

function SyncReport({ result }: { result: SyncResponse }) {
  const counts = Object.entries(SYNC_LABELS)
    .filter(([key]) => result.summary[key] > 0)
    .map(([key, label]) => `${label} ${result.summary[key]}`);
  return (
    <section className="notice">
      <p>동기화 완료: {counts.length > 0 ? counts.join(" · ") : "개념 없음"}</p>
      {result.errors.length > 0 && (
        <>
          <p className="error">읽지 못한 파일</p>
          <ul>
            {result.errors.map((e, i) => (
              <li key={i}>{e.source_ref}: {e.message}</li>
            ))}
          </ul>
        </>
      )}
      {result.dangling_refs.length > 0 && (
        <>
          <p>없는 개념을 가리키는 연결</p>
          <ul>
            {result.dangling_refs.map((r, i) => (
              <li key={i}>{r.concept_id} → {r.ref}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

function DueList({ cards, onSelect }: { cards: DueCard[]; onSelect: (card: DueCard) => void }) {
  if (cards.length === 0) {
    return <p className="muted">지금 복습할 카드가 없습니다. 개념 파일을 추가했다면 동기화하세요.</p>;
  }
  return (
    <section>
      <h2>복습할 카드 {cards.length}장</h2>
      <ul className="cards">
        {cards.map((card) => (
          <li key={card.card_id}>
            <button className="card" onClick={() => onSelect(card)}>
              <span className="concept">{card.concept_id} · {card.concept_title}</span>
              <span>{card.question}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
