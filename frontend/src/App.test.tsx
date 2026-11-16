import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

const CARD = {
  card_id: 7,
  concept_id: "NET-010",
  concept_title: "Static Routing",
  question: "정적 라우팅이란?",
  due_at: "2026-11-16T09:00:00+09:00",
};

const QUESTION = {
  question_id: 3,
  card_id: 7,
  concept_id: "NET-010",
  base_question: CARD.question,
  question: "변형 질문",
  relative_difficulty: 1,
  difficulty_reason: "장애 상황이 추가됐다",
  created_at: "2026-11-16T10:00:00+09:00",
};

const EVALUATION = {
  submission_id: 1,
  score: 72,
  accuracy: 80,
  completeness: 70,
  logic: 75,
  technical_validity: 85,
  application: 65,
  strengths: ["핵심을 짚음"],
  missing_points: ["왕복 경로 누락"],
  technical_errors: [],
  recommended_lab: "LAB-002",
  model: "fake-model",
  submitted_at: "2026-11-16T10:05:00+09:00",
};

type Route = () => [number, unknown];

// "메서드 경로"별 응답을 정해 둔 가짜 fetch. 보낸 요청을 기록한다
function mockApi(routes: Record<string, Route>) {
  const calls: { route: string; body: unknown }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${path}`;
      calls.push({ route, body: init?.body ? JSON.parse(init.body as string) : undefined });
      const [status, body] = routes[route]?.() ?? [404, { detail: "없는 경로" }];
      return new Response(JSON.stringify(body), { status });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("카드를 골라 AI 질문 → 답안 → 평가 → 등급까지 진행한다", async () => {
  let due = [CARD];
  const calls = mockApi({
    "GET /reviews/due": () => [200, due],
    "POST /cards/7/questions": () => [201, QUESTION],
    "POST /questions/3/answers": () => [201, EVALUATION],
    "POST /reviews": () => {
      due = [];
      return [200, { card_id: 7, rating: 3, reviewed_at: "2026-11-16T10:06:00+09:00", next_due_at: "2026-11-19T10:06:00+09:00" }];
    },
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: /정적 라우팅이란/ }));
  await user.click(screen.getByRole("button", { name: "AI 질문 받기" }));
  expect(await screen.findByRole("heading", { name: "변형 질문" })).toBeTruthy();
  expect(screen.getByText(/난이도 어려움 .* 장애 상황이 추가됐다/)).toBeTruthy();

  await user.type(screen.getByLabelText("답안"), "다음 홉을 지정한다");
  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  expect(await screen.findByText("왕복 경로 누락")).toBeTruthy();
  expect(screen.getByText("85")).toBeTruthy(); // 기술적 타당성
  expect(screen.getByText("추천 실습: LAB-002")).toBeTruthy();
  expect(screen.queryByText("기술적 오류")).toBeNull(); // 빈 목록은 숨긴다

  await user.click(screen.getByRole("button", { name: /Good/ }));
  expect(await screen.findByText(/다음 복습: 2026\. 11\. 19\./)).toBeTruthy();
  expect(await screen.findByText(/지금 복습할 카드가 없습니다/)).toBeTruthy();

  expect(calls.find((c) => c.route === "POST /questions/3/answers")?.body).toEqual({ answer: "다음 홉을 지정한다" });
  expect(calls.find((c) => c.route === "POST /reviews")?.body).toEqual({ card_id: 7, rating: 3 });
});

test("API 오류 메시지를 보여 주고 다시 시도할 수 있다", async () => {
  let attempts = 0;
  mockApi({
    "GET /reviews/due": () => [200, [CARD]],
    "POST /cards/7/questions": () =>
      ++attempts === 1 ? [503, { detail: "LLM이 설정되지 않았습니다 (GEMINI_API_KEY)" }] : [201, QUESTION],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: /정적 라우팅이란/ }));
  await user.click(screen.getByRole("button", { name: "AI 질문 받기" }));
  expect((await screen.findByRole("alert")).textContent).toContain("GEMINI_API_KEY");

  await user.click(screen.getByRole("button", { name: "AI 질문 받기" }));
  expect(await screen.findByRole("heading", { name: "변형 질문" })).toBeTruthy();
  expect(screen.queryByRole("alert")).toBeNull();
});

test("동기화 결과와 읽지 못한 파일을 보여 주고 목록을 다시 불러온다", async () => {
  let due: (typeof CARD)[] = [];
  mockApi({
    "GET /reviews/due": () => [200, due],
    "POST /sync/markdown": () => {
      due = [CARD];
      return [200, {
        dry_run: false,
        summary: { created: 3, updated: 0, relocated: 0, restored: 0, archived: 0, unchanged: 1, kept_due_to_error: 0, errors: 1, dangling_refs: 0 },
        errors: [{ source_ref: "network/bad.md", message: "질문이 3개 미만입니다" }],
        dangling_refs: [],
      }];
    },
  });
  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByText(/지금 복습할 카드가 없습니다/)).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "개념 동기화" }));
  expect(await screen.findByText("동기화 완료: 새로 추가 3 · 변경 없음 1")).toBeTruthy();
  expect(screen.getByText("network/bad.md: 질문이 3개 미만입니다")).toBeTruthy();
  expect(await screen.findByText("복습할 카드 1장")).toBeTruthy();
});
