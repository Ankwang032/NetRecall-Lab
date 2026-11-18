import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
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
const CARD2 = { ...CARD, card_id: 8, question: "다음 홉이란?" };

const ORIGINAL = {
  question_id: 3,
  card_id: 7,
  concept_id: "NET-010",
  base_question: CARD.question,
  question: CARD.question,
  kind: "original",
  relative_difficulty: null,
  difficulty_reason: null,
  created_at: "2026-11-16T10:00:00+09:00",
};
const VARIANT = {
  ...ORIGINAL,
  question_id: 4,
  question: "변형 질문",
  kind: "variant",
  relative_difficulty: 1,
  difficulty_reason: "장애 상황이 추가됐다",
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

const REVIEWED = {
  card_id: 7,
  rating: 3,
  reviewed_at: "2026-11-16T10:06:00+09:00",
  next_due_at: "2026-11-19T10:06:00+09:00",
};

type Route = (body: any) => [number, unknown];

// "메서드 경로"별 응답을 정해 둔 가짜 fetch. 보낸 요청을 기록한다
function mockApi(routes: Record<string, Route>) {
  const calls: { route: string; body: any }[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (path: string, init?: RequestInit) => {
      const route = `${init?.method ?? "GET"} ${path}`;
      const body = init?.body ? JSON.parse(init.body as string) : undefined;
      calls.push({ route, body });
      const [status, data] = routes[route]?.(body) ?? [404, { detail: `없는 경로: ${route}` }];
      return new Response(JSON.stringify(data), { status });
    }),
  );
  return calls;
}

const count = (calls: { route: string }[], route: string) => calls.filter((c) => c.route === route).length;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test("원래 질문 → AI 평가 → 변형 질문 → AI 평가 → 등급 → 다음 카드", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, [CARD, CARD2]],
    "POST /cards/7/questions/original": () => [201, ORIGINAL],
    "POST /questions/3/answers": () => [201, EVALUATION],
    "POST /cards/7/questions": () => [201, VARIANT],
    "POST /questions/4/answers": () => [201, { ...EVALUATION, score: 90, missing_points: [] }],
    "POST /reviews": () => [200, REVIEWED],
  });
  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByText("카드 2장 · 개념 1개")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "학습 시작" }));

  // 1차: 원래 질문에 바로 답한다
  expect(screen.getByRole("heading", { name: CARD.question })).toBeTruthy();
  await user.type(screen.getByLabelText("내 답안"), "1차 답안");
  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  expect(await screen.findByText("왕복 경로 누락")).toBeTruthy();
  expect(screen.getByText("85")).toBeTruthy(); // 기술적 타당성
  expect(screen.getByText("보통")).toBeTruthy();
  expect(screen.queryByText("기술적 오류")).toBeNull(); // 빈 목록은 숨긴다

  // 2차: 필요하면 변형 질문을 받는다
  await user.click(screen.getByRole("button", { name: "변형 질문 받기" }));
  expect(await screen.findByRole("heading", { name: "변형 질문" })).toBeTruthy();
  expect(screen.getByText("난이도 어려움")).toBeTruthy();
  expect(screen.getByText("장애 상황이 추가됐다")).toBeTruthy();
  await user.type(screen.getByLabelText("내 답안"), "2차 답안");
  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  expect(await screen.findByText("90")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: /Good/ }));
  expect(await screen.findByText(/다음 복습: 11월 19일/)).toBeTruthy();
  expect(await screen.findByRole("heading", { name: CARD2.question })).toBeTruthy(); // 다음 카드
  expect(screen.getByText("2 / 2")).toBeTruthy();

  expect(calls.find((c) => c.route === "POST /questions/3/answers")?.body).toEqual({ answer: "1차 답안" });
  expect(calls.find((c) => c.route === "POST /questions/4/answers")?.body).toEqual({ answer: "2차 답안" });
  expect(calls.find((c) => c.route === "POST /reviews")?.body).toEqual({ card_id: 7, rating: 3 });
});

test("1차 평가만 보고 등급을 고르면 마지막 카드 뒤 목록으로 돌아간다", async () => {
  let due = [CARD];
  const calls = mockApi({
    "GET /reviews/due": () => [200, due],
    "POST /cards/7/questions/original": () => [201, ORIGINAL],
    "POST /questions/3/answers": () => [201, EVALUATION],
    "POST /reviews": () => {
      due = [];
      return [200, REVIEWED];
    },
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: CARD.question }));
  await user.type(screen.getByLabelText("내 답안"), "답안");
  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  await user.click(await screen.findByRole("button", { name: /Again/ }));

  expect(await screen.findByText("이번 학습을 마쳤습니다")).toBeTruthy();
  expect(await screen.findByText("지금 복습할 카드가 없습니다")).toBeTruthy();
  expect(count(calls, "POST /cards/7/questions")).toBe(0); // 변형 질문은 요청하지 않았다
  expect(calls.find((c) => c.route === "POST /reviews")?.body).toEqual({ card_id: 7, rating: 1 });
});

test("평가가 실패하면 답안을 남겨 두고, 다시 내도 원래 질문을 또 만들지 않는다", async () => {
  let attempts = 0;
  const calls = mockApi({
    "GET /reviews/due": () => [200, [CARD]],
    "POST /cards/7/questions/original": () => [201, ORIGINAL],
    "POST /questions/3/answers": () =>
      ++attempts === 1 ? [502, { detail: "Gemini 사용량 한도를 넘었습니다. 1분쯤 뒤에 다시 시도하세요." }] : [201, EVALUATION],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: CARD.question }));
  await user.type(screen.getByLabelText("내 답안"), "지우면 안 되는 답안");
  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  expect((await screen.findByRole("alert")).textContent).toContain("한도를 넘었습니다");
  expect((screen.getByLabelText("내 답안") as HTMLTextAreaElement).value).toBe("지우면 안 되는 답안");

  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  expect(await screen.findByText("왕복 경로 누락")).toBeTruthy();
  expect(count(calls, "POST /cards/7/questions/original")).toBe(1);
});

test("동기화 결과를 알리고 읽지 못한 파일을 보여 준 뒤 목록을 다시 불러온다", async () => {
  let due: (typeof CARD)[] = [];
  mockApi({
    "GET /reviews/due": () => [200, due],
    "POST /sync/markdown": () => {
      due = [CARD];
      return [200, {
        dry_run: false,
        summary: { created: 3, updated: 0, relocated: 0, restored: 0, archived: 0, unchanged: 1, kept_due_to_error: 0, errors: 1, dangling_refs: 0 },
        errors: [{ source_ref: "network/bad.md", message: "질문이 3개 이상 필요합니다" }],
        dangling_refs: [],
      }];
    },
  });
  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByText("지금 복습할 카드가 없습니다")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "동기화" }));
  expect(await screen.findByText("새로 추가 3 · 변경 없음 1")).toBeTruthy();
  expect(screen.getByText("동기화하지 못한 파일 1개")).toBeTruthy();
  expect(screen.getByText("network/bad.md")).toBeTruthy();
  expect(await screen.findByText("카드 1장 · 개념 1개")).toBeTruthy();
});

test("md 파일을 올리면 검사 결과를 보여 주고, 모두 통과해야 저장된다", async () => {
  const OSPF = "---\nid: NET-020\ntitle: OSPF\n---\nOSPF 본문\n";
  let due: (typeof CARD)[] = [];
  const check = (name: string) =>
    name === "ospf.md"
      ? { name, path: `network/${name}`, concept_id: "NET-020", title: "OSPF", question_count: 3, errors: [] }
      : { name, path: `network/${name}`, concept_id: null, title: null, question_count: 0, errors: ["frontmatter(--- 블록)가 없습니다"] };
  const calls = mockApi({
    "GET /reviews/due": () => [200, due],
    "GET /concepts/folders": () => [200, ["", "network"]],
    "POST /concepts/files?dry_run=true": (body) =>
      [200, { saved: false, files: body.files.map((f: { name: string }) => check(f.name)), sync: null }],
    "POST /concepts/files": (body) => {
      due = [CARD];
      return [200, { saved: true, files: body.files.map((f: { name: string }) => check(f.name)), sync: null }];
    },
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "개념 추가" }));
  const dialog = await screen.findByRole("dialog");
  await user.upload(within(dialog).getByLabelText(/끌어다 놓거나/), [
    new File([OSPF], "ospf.md", { type: "text/markdown" }),
    new File(["본문만"], "bad.md", { type: "text/markdown" }),
  ]);

  expect(await within(dialog).findByText("frontmatter(--- 블록)가 없습니다")).toBeTruthy();
  expect(within(dialog).getByText(/통과 · NET-020 OSPF · 질문 3개/)).toBeTruthy();
  const saveButton = within(dialog).getByRole("button", { name: "2개 저장" }) as HTMLButtonElement;
  expect(saveButton.disabled).toBe(true);

  await user.click(within(dialog).getByRole("button", { name: "bad.md 빼기" }));
  const save = within(dialog).getByRole("button", { name: "1개 저장" }) as HTMLButtonElement;
  await waitFor(() => expect(save.disabled).toBe(false));
  await user.click(save);

  expect(await screen.findByText("개념 1개를 추가했습니다")).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(await screen.findByText("카드 1장 · 개념 1개")).toBeTruthy();
  expect(calls.find((c) => c.route === "POST /concepts/files")?.body).toEqual({
    folder: "",
    files: [{ name: "ospf.md", content: OSPF }],
  });
});
