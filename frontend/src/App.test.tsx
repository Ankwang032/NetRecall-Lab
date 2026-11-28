import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { App } from "./App";

// xterm은 jsdom에서 그릴 수 없다. 터미널 탭 동작만 본다 (연결은 서버 테스트와 실제 확인에서)
vi.mock("@/components/LabTerminal", () => ({
  default: ({ node, shell, active }: { node: string; shell: string; active: boolean }) => (
    <p>{`터미널 ${node} ${shell}${active ? " (보는 중)" : ""}`}</p>
  ),
}));

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
  window.history.replaceState(null, "", "/"); // 다음 테스트는 첫 화면에서 시작한다
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

test("주제(카테고리)를 고르면 그 주제의 카드만 학습하고, 돌아와도 고른 주제가 남는다", async () => {
  const routing = [{ ...CARD, category: "라우팅" }, { ...CARD2, category: "라우팅" }];
  const basics = { ...CARD, card_id: 9, concept_id: "NET-005", concept_title: "IP 주소", category: "네트워크 기본", question: "서브넷이란?" };
  mockApi({ "GET /reviews/due": () => [200, [basics, ...routing]] });
  const user = userEvent.setup();
  render(<App />);

  const topics = await screen.findByRole("group", { name: "주제" });
  expect(within(topics).getAllByRole("button").map((b) => b.textContent)).toEqual(["전체3", "라우팅2", "네트워크 기본1"]);
  await user.click(within(topics).getByRole("button", { name: /라우팅/ }));
  expect(within(topics).getByRole("button", { name: /라우팅/ }).getAttribute("aria-pressed")).toBe("true");
  expect(screen.getByText("라우팅 · 카드 2장 · 개념 1개")).toBeTruthy();
  expect(screen.queryByText("서브넷이란?")).toBeNull();

  await user.click(screen.getByRole("button", { name: "라우팅 학습 시작" }));
  expect(screen.getByRole("heading", { name: CARD.question })).toBeTruthy();
  expect(screen.getByText("1 / 2")).toBeTruthy(); // 네트워크 기본 카드는 빠졌다

  await user.click(screen.getByRole("button", { name: "목록" }));
  expect(await screen.findByText("라우팅 · 카드 2장 · 개념 1개")).toBeTruthy();
});

test("개념 묶음의 '이 개념만'은 그 개념의 카드만 학습한다", async () => {
  const other = { ...CARD, card_id: 9, concept_id: "NET-005", concept_title: "IP 주소", question: "서브넷이란?" };
  mockApi({ "GET /reviews/due": () => [200, [CARD, other, CARD2]] });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "이 개념만 학습 (Static Routing)" }));
  expect(screen.getByRole("heading", { name: CARD.question })).toBeTruthy();
  expect(screen.getByText("1 / 2")).toBeTruthy();
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
        warnings: [],
        dangling_refs: [],
      }];
    },
    "POST /sync/notion": () => [503, { detail: "Notion이 설정되지 않았습니다 (NOTION_TOKEN)" }], // 설정 안 됨 → 조용히 건너뜀
  });
  const user = userEvent.setup();
  render(<App />);

  expect(await screen.findByText("지금 복습할 카드가 없습니다")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "동기화" }));
  expect(await screen.findByText("새로 추가 3 · 변경 없음 1")).toBeTruthy();
  expect(screen.getByText("동기화하지 못한 항목 1개")).toBeTruthy();
  expect(screen.getByText("network/bad.md")).toBeTruthy();
  expect(await screen.findByText("카드 1장 · 개념 1개")).toBeTruthy();
  expect(screen.queryByText("Notion을 동기화하지 못했습니다")).toBeNull();
});

const syncResult = (summary: Record<string, number>, extra: Record<string, unknown> = {}) =>
  ({ dry_run: false, summary, errors: [], warnings: [], dangling_refs: [], ...extra });

test("Notion 데이터베이스가 설정되어 있으면 이어서 동기화하고 결과를 함께 보여 준다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "POST /sync/markdown": () => [200, syncResult({ unchanged: 3 })],
    "POST /sync/notion": () => [200, syncResult({ created: 11, taken_over: 1 }, {
      errors: [{ source_ref: "page-id-1", message: "IPv4 주소: 난이도는 1~5 정수여야 합니다" }],
      warnings: [{ source_ref: "page-id-2", message: "정적 라우팅: Notion이 내보내지 못한 블록 1개를 뺐습니다" }],
    })],
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "동기화" }));

  expect(await screen.findByText("Markdown 변경 없음 3 / Notion 새로 추가 11 · 넘겨받음 1")).toBeTruthy();
  expect(screen.getByText("동기화하지 못한 항목 1개")).toBeTruthy();
  expect(screen.getByText(/IPv4 주소: 난이도는 1~5 정수여야 합니다/)).toBeTruthy();
  expect(screen.getByText(/정적 라우팅: Notion이 내보내지 못한 블록 1개를 뺐습니다/)).toBeTruthy();
  expect(screen.queryByText("page-id-1")).toBeNull(); // 페이지 id 대신 "Notion"
  expect(screen.getAllByText("Notion")).toHaveLength(2);
  expect(calls.map((c) => c.route).filter((r) => r.startsWith("POST /sync"))).toEqual(["POST /sync/markdown", "POST /sync/notion"]);
});

test("Notion 동기화가 실패해도 Markdown 결과는 반영하고 오류를 알린다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "POST /sync/markdown": () => [200, syncResult({ created: 1 })],
    "POST /sync/notion": () => [502, { detail: "Notion 서버가 응답하지 않습니다 (502)." }],
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "동기화" }));

  expect(await screen.findByText("Notion을 동기화하지 못했습니다")).toBeTruthy();
  expect(screen.getByText("Notion 서버가 응답하지 않습니다 (502).")).toBeTruthy();
  expect(await screen.findByText("새로 추가 1")).toBeTruthy();
});

const OSPF = "---\nid: NET-020\ntitle: OSPF\n---\nOSPF 본문\n";
const passed = (name: string, concept_id: string, title: string) =>
  ({ name, path: `network/${name}`, concept_id, title, question_count: 3, errors: [] });
const plan = (name: string, status: string, extra: Record<string, unknown> = {}) =>
  ({ name, status, concept_id: null, title: null, warnings: [], error: null, ...extra });

async function openDialog() {
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "개념 추가" }));
  return { user, dialog: await screen.findByRole("dialog") };
}

test("md 파일을 올리면 계획·검사 결과를 보여 주고, 모두 통과해야 저장된다", async () => {
  let due: (typeof CARD)[] = [];
  const calls = mockApi({
    "GET /reviews/due": () => [200, due],
    "GET /concepts/folders": () => [200, ["", "network"]],
    "POST /concepts/normalize/plan": (body) => [200, {
      files: body.files.map((f: { name: string }) =>
        f.name === "ospf.md"
          ? plan(f.name, "standard", { concept_id: "NET-020", title: "OSPF" })
          : plan(f.name, "failed", { error: "본문이 비어 있습니다" })),
    }],
    "POST /concepts/files?dry_run=true": (body) =>
      [200, { saved: false, files: body.files.map((f: { name: string }) => passed(f.name, "NET-020", "OSPF")), sync: null }],
    "POST /concepts/files": (body) => {
      due = [CARD];
      return [200, { saved: true, files: body.files.map((f: { name: string }) => passed(f.name, "NET-020", "OSPF")), sync: null }];
    },
  });
  const { user, dialog } = await openDialog();
  await user.upload(within(dialog).getByLabelText(/끌어다 놓거나/), [
    new File([OSPF], "ospf.md", { type: "text/markdown" }),
    new File(["---\nid: NET-030\n---\n"], "empty.md", { type: "text/markdown" }),
  ]);

  expect(await within(dialog).findByText("본문이 비어 있습니다")).toBeTruthy();
  const saveButton = within(dialog).getByRole("button", { name: "2개 저장" }) as HTMLButtonElement;
  expect(saveButton.disabled).toBe(true);
  expect(count(calls, "POST /concepts/files?dry_run=true")).toBe(0); // 쓸 수 없는 파일이 있으면 검사하지 않는다

  await user.click(within(dialog).getByRole("button", { name: "empty.md 빼기" }));
  expect(await within(dialog).findByText(/통과 · NET-020 OSPF · 질문 3개/)).toBeTruthy();
  const save = within(dialog).getByRole("button", { name: "1개 저장" }) as HTMLButtonElement;
  await waitFor(() => expect(save.disabled).toBe(false));
  await user.click(save);

  expect(await screen.findByText("개념 1개를 추가했습니다")).toBeTruthy();
  await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(await screen.findByText("카드 1장 · 개념 1개")).toBeTruthy();
  expect(calls.filter((c) => c.route === "POST /concepts/normalize/plan").at(-1)?.body).toEqual({
    files: [{ name: "ospf.md", content: OSPF }],
  });
  expect(calls.find((c) => c.route === "POST /concepts/files")?.body).toEqual({
    folder: "",
    files: [{ name: "ospf.md", content: OSPF }],
  });
});

test("형식이 다른 파일은 AI로 맞춘 내용을 검사하고 저장한다", async () => {
  const NOTE = "# 정적 라우팅\n\n본문\n\n## 질문\n- 하나\n- 둘\n- 셋\n";
  const CONVERTED = "---\nid: NET-011\ntitle: 정적 라우팅\n---\n\n# 정적 라우팅\n\n본문\n";
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts/folders": () => [200, [""]],
    "POST /concepts/normalize/plan": (body) => [200, {
      files: body.files.map((f: { name: string }) => f.name === "routing.md"
        ? plan(f.name, "convert", { concept_id: "NET-011", title: "정적 라우팅", warnings: ["모르는 frontmatter 키를 버렸습니다: aliases"] })
        : plan(f.name, "standard", { concept_id: "NET-020", title: "OSPF" })),
    }],
    "POST /concepts/normalize/convert": (body) => [200, {
      name: body.file.name, concept_id: body.concept_id, title: "정적 라우팅", content: CONVERTED,
      warnings: ["선수 개념 NET-999는 없어서 뺐습니다"],
    }],
    "POST /concepts/files?dry_run=true": (body) => [200, {
      saved: false, sync: null,
      files: body.files.map((f: { name: string }) =>
        f.name === "routing.md" ? passed(f.name, "NET-011", "정적 라우팅") : passed(f.name, "NET-020", "OSPF")),
    }],
    "POST /concepts/files": (body) => [200, { saved: true, files: body.files.map((f: { name: string }) => passed(f.name, "X", "X")), sync: null }],
  });
  const { user, dialog } = await openDialog();
  await user.upload(within(dialog).getByLabelText(/끌어다 놓거나/), [
    new File([NOTE], "routing.md", { type: "text/markdown" }),
    new File([OSPF], "ospf.md", { type: "text/markdown" }),
  ]);

  expect(await within(dialog).findByText("형식 맞추기 필요 · NET-011 정적 라우팅")).toBeTruthy();
  expect(within(dialog).getByText("모르는 frontmatter 키를 버렸습니다: aliases")).toBeTruthy();
  expect(count(calls, "POST /concepts/files?dry_run=true")).toBe(0); // 맞추기 전에는 검사하지 않는다

  await user.click(within(dialog).getByRole("button", { name: "형식 맞추기 (AI 1번)" }));
  expect(await within(dialog).findByText(/통과 · NET-011 정적 라우팅/)).toBeTruthy();
  expect(within(dialog).getByText("AI로 맞춤")).toBeTruthy();
  expect(within(dialog).getByText("선수 개념 NET-999는 없어서 뺐습니다")).toBeTruthy();

  const convert = calls.find((c) => c.route === "POST /concepts/normalize/convert")?.body;
  expect(convert).toEqual({
    file: { name: "routing.md", content: NOTE },
    concept_id: "NET-011",
    batch: [{ concept_id: "NET-020", title: "OSPF" }], // 함께 올린 다른 파일
  });
  const check = calls.find((c) => c.route === "POST /concepts/files?dry_run=true")?.body;
  expect(check.files).toEqual([{ name: "routing.md", content: CONVERTED }, { name: "ospf.md", content: OSPF }]);

  const save = within(dialog).getByRole("button", { name: "2개 저장" }) as HTMLButtonElement;
  await waitFor(() => expect(save.disabled).toBe(false));
  await user.click(save);
  expect(await screen.findByText("개념 2개를 추가했습니다")).toBeTruthy();
});

test("AI 변환이 실패하면 멈추고, 다시 누르면 남은 파일부터 한다", async () => {
  let fail = true;
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts/folders": () => [200, [""]],
    "POST /concepts/normalize/plan": (body) => [200, {
      files: body.files.map((f: { name: string }, i: number) =>
        plan(f.name, "convert", { concept_id: `NET-01${i + 1}`, title: f.name })),
    }],
    "POST /concepts/normalize/convert": (body) => {
      if (fail) return [502, { detail: "Gemini 모델에 요청이 몰려 지금은 응답하지 못합니다." }];
      return [200, { name: body.file.name, concept_id: body.concept_id, title: body.file.name, content: `---\nid: ${body.concept_id}\n---\n본문\n`, warnings: [] }];
    },
    "POST /concepts/files?dry_run=true": (body) =>
      [200, { saved: false, files: body.files.map((f: { name: string }) => passed(f.name, "NET-011", f.name)), sync: null }],
  });
  const { user, dialog } = await openDialog();
  await user.upload(within(dialog).getByLabelText(/끌어다 놓거나/), [
    new File(["# 가\n본문"], "a.md", { type: "text/markdown" }),
    new File(["# 나\n본문"], "b.md", { type: "text/markdown" }),
  ]);
  await user.click(await within(dialog).findByRole("button", { name: "형식 맞추기 (AI 2번)" }));

  expect(await within(dialog).findByText(/형식을 맞추지 못했습니다: Gemini 모델에 요청이 몰려/)).toBeTruthy();
  expect(count(calls, "POST /concepts/normalize/convert")).toBe(1); // 두 번째 파일은 부르지 않았다

  fail = false;
  await user.click(within(dialog).getByRole("button", { name: "형식 맞추기 (AI 2번)" }));
  expect(await within(dialog).findAllByText("AI로 맞춤")).toHaveLength(2);
  expect(count(calls, "POST /concepts/normalize/convert")).toBe(3);
  expect(await within(dialog).findByRole("button", { name: "2개 저장" })).toBeTruthy();
});

test("Notion 페이지 주소로 하위 페이지를 골라 가져온다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts/folders": () => [200, [""]],
    "GET /notion/pages?parent=https%3A%2F%2Fwww.notion.so%2Fnet-abc": () => [200, {
      parent: { page_id: "p0", title: "🌐 네트워크" },
      pages: [{ page_id: "p1", title: "정적 라우팅" }, { page_id: "p2", title: "OSI 7계층" }, { page_id: "p3", title: "비공개" }],
    }],
    "POST /notion/files": (body) => [200, {
      files: body.page_ids.map((id: string) => id === "p1"
        ? { page_id: id, title: "정적 라우팅", name: "정적-라우팅.md", content: "# 정적 라우팅\n\n본문", warnings: ["Notion이 페이지를 끝까지 돌려주지 못했습니다"], error: null }
        : { page_id: id, title: "", name: "", content: null, warnings: [], error: "페이지를 찾을 수 없습니다" }),
    }],
    "POST /concepts/normalize/plan": (body) => [200, {
      files: body.files.map((f: { name: string }) => plan(f.name, "convert", { concept_id: "NET-011", title: "정적 라우팅" })),
    }],
  });
  const { user, dialog } = await openDialog();
  await user.click(within(dialog).getByRole("tab", { name: "Notion에서 가져오기" }));
  await user.type(within(dialog).getByLabelText("Notion 페이지 주소"), "https://www.notion.so/net-abc");
  await user.click(within(dialog).getByRole("button", { name: "불러오기" }));

  await user.click(await within(dialog).findByRole("checkbox", { name: "OSI 7계층" })); // 3개 중 하나를 뺀다
  await user.click(within(dialog).getByRole("button", { name: "2개 가져오기" }));

  expect(await within(dialog).findByText("가져오지 못한 페이지 1개")).toBeTruthy();
  expect(within(dialog).getByText("페이지를 찾을 수 없습니다")).toBeTruthy();
  expect(await within(dialog).findByText("형식 맞추기 필요 · NET-011 정적 라우팅")).toBeTruthy();
  expect(within(dialog).getByText("Notion이 페이지를 끝까지 돌려주지 못했습니다")).toBeTruthy();
  expect(within(dialog).queryByRole("list", { name: "Notion 페이지" })).toBeNull(); // 가져온 뒤 목록을 닫는다
  expect(calls.find((c) => c.route === "POST /notion/files")?.body).toEqual({ page_ids: ["p1", "p3"] });
  expect(calls.find((c) => c.route === "POST /concepts/normalize/plan")?.body).toEqual({
    files: [{ name: "정적-라우팅.md", content: "# 정적 라우팅\n\n본문" }],
  });
});

test("하위 페이지가 없으면 그 페이지를 가져오고, Notion 오류는 그대로 보여 준다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts/folders": () => [200, [""]],
    "GET /notion/pages?parent=leaf": () => [200, { parent: { page_id: "p9", title: "정적 라우팅" }, pages: [] }],
    "GET /notion/pages?parent=nope": () => [503, { detail: "NOTION_TOKEN이 설정되지 않았습니다" }],
  });
  const { user, dialog } = await openDialog();
  await user.click(within(dialog).getByRole("tab", { name: "Notion에서 가져오기" }));
  const address = within(dialog).getByLabelText("Notion 페이지 주소");

  await user.type(address, "nope");
  await user.click(within(dialog).getByRole("button", { name: "불러오기" }));
  expect(await within(dialog).findByText("NOTION_TOKEN이 설정되지 않았습니다")).toBeTruthy();

  await user.clear(address);
  await user.type(address, "leaf");
  await user.click(within(dialog).getByRole("button", { name: "불러오기" }));
  const box = (await within(dialog).findByRole("checkbox", { name: "정적 라우팅" })) as HTMLButtonElement;
  expect(box.getAttribute("data-state")).toBe("checked");
  expect(within(dialog).getByRole("button", { name: "1개 가져오기" })).toBeTruthy();
});

// ---- 실습 화면 ----

const LAB_LIST = {
  scenarios: [
    {
      id: "LAB-001", title: "대역의 첫 주소와 마지막 주소로 통신하기", type: "build", concepts: ["NET-005"],
      time_limit_minutes: 60,
      last_run: {
        run_id: 1, status: "passed", level: "normal", attempts: 2, hints_used: 1, started_at: "2026-11-25T14:00:00+09:00",
        passed_at: "2026-11-25T14:12:00+09:00", finished_at: "2026-11-25T14:13:00+09:00",
      },
    },
    { id: "LAB-002", title: "라우터 두 대 너머로 통신하기", type: "build", concepts: ["NET-010"], time_limit_minutes: 60, last_run: null },
  ],
  errors: [],
};

const RUN = {
  run_id: 3, scenario_id: "LAB-002", title: "라우터 두 대 너머로 통신하기", status: "active",
  goal: "PC1과 PC2가 서로 ping되게 하라. 동적 라우팅 프로토콜은 쓰지 않는다.",
  networks: { lan1: "10.1.2.0/24", lan2: "10.3.4.0/24", transit: "172.16.0.0/30" },
  addresses: [
    { interface: "pc1:eth1", address: "10.1.2.10/24" },
    { interface: "r1:eth1", address: "10.1.2.1/24" },
    { interface: "r1:eth2", address: "172.16.0.1/30" },
  ],
  nodes: [
    { name: "pc1", kind: "host", connect: "docker exec -it clab-nr-3-pc1 sh" },
    { name: "r1", kind: "router", connect: "docker exec -it clab-nr-3-r1 vtysh" },
    { name: "r2", kind: "router", connect: "docker exec -it clab-nr-3-r2 vtysh" },
  ],
  links: [{ a: "pc1:eth1", b: "r1:eth1" }, { a: "r1:eth2", b: "r2:eth2" }],
  level: "normal", hint_limit: 2,
  checks: [
    { id: "pc1-to-pc2", description: "PC1 → PC2 ping" },
    { id: "r1-route", description: "R1이 LAN2로 갈 때 직접 넣은 경로를 쓴다" },
  ],
  attempts: 0, hints_used: 0, hints: {}, last_attempt: null,
  started_at: "2026-11-26T13:00:00+09:00", expires_at: new Date(Date.now() + 42 * 60_000).toISOString(),
  passed_at: null, finished_at: null, error: null,
};

const ATTEMPT = {
  attempt_id: 1, run_id: 3, run_status: "active", passed: false, attempted_at: "2026-11-26T13:10:00+09:00",
  passed_count: 1, total_count: 3,
  results: [
    { check_id: "pc1-to-pc2", description: "PC1 → PC2 ping", kind: "ping", passed: false,
      message: "10.3.4.10에서 응답이 없습니다", output: "3 packets transmitted, 0 received, 100% packet loss" },
    { check_id: "r1-route", description: "R1이 LAN2로 갈 때 직접 넣은 경로를 쓴다", kind: "route", passed: false,
      message: "10.3.4.10으로 가는 경로가 없습니다", output: "" },
    { check_id: "auto:unique-addresses", description: "검사가 가리키는 주소가 의도한 인터페이스에만 있다", kind: "unique",
      passed: true, message: "", output: "" },
  ],
};

const FINISHED = { ...RUN, status: "abandoned", finished_at: "2026-11-26T13:20:00+09:00" };

function openLabs(path = "/labs") {
  window.history.pushState(null, "", path);
  render(<App />);
}

test("사이드바로 실습 목록을 열고, 도움 수준을 골라 시작하면 실행 화면을 보여 준다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, null],
    "GET /labs": () => [200, LAB_LIST],
    "POST /labs/LAB-002/runs": () => [201, RUN],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("link", { name: "실습" }));
  expect(await screen.findByRole("heading", { name: "실습" })).toBeTruthy();
  const [first, second] = screen.getAllByRole("listitem");
  expect(within(first).getByText("통과")).toBeTruthy(); // 마지막 실행 결과
  expect(within(first).getByText(/시도 2번 · 힌트 1번/)).toBeTruthy();
  expect(within(second).getByText("아직 해 보지 않았습니다")).toBeTruthy();

  await user.click(within(second).getByRole("button", { name: "시작" }));
  const dialog = await screen.findByRole("dialog", { name: "LAB-002 시작" });
  expect((within(dialog).getByRole("radio", { name: /보통/ }) as HTMLInputElement).checked).toBe(true);
  await user.click(within(dialog).getByRole("radio", { name: /쉬움/ }));
  await user.click(within(dialog).getByRole("button", { name: "시작" }));

  expect(await screen.findByRole("heading", { name: RUN.title })).toBeTruthy();
  expect(calls.find((c) => c.route === "POST /labs/LAB-002/runs")?.body).toEqual({ level: "easy" });
  expect(screen.getByText("172.16.0.0/30")).toBeTruthy();
  expect(screen.getByRole("group", { name: /토폴로지: pc1:eth1 — r1:eth1, r1:eth2 — r2:eth2, pc1:eth1 10.1.2.10\/24/ })).toBeTruthy();
  expect(screen.getByText(/남은 시간/)).toBeTruthy();
  expect(screen.getAllByText("검증 전")).toHaveLength(2);

  await user.click(screen.getByRole("button", { name: "r1 접속 명령 복사" }));
  expect(await navigator.clipboard.readText()).toBe("docker exec -it clab-nr-3-r1 vtysh");
});

test("검증 결과를 검사별로 보여 주고, 힌트를 한 단계씩 연다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, RUN],
    "GET /labs": () => [200, LAB_LIST],
    "POST /lab-runs/3/attempts": () => [201, ATTEMPT],
    "GET /lab-runs/3": () => [200, { ...RUN, attempts: 1, last_attempt: ATTEMPT }],
    "POST /lab-runs/3/hints": (body) => [200, {
      check_id: body.check_id, number: 2, description: "R1이 LAN2로 갈 때 직접 넣은 경로를 쓴다",
      hints: ["라우터는 직접 연결된 대역만 압니다."], new: true, limit: 2, total: 3,
    }],
  });
  const user = userEvent.setup();
  openLabs();

  await user.click(await screen.findByRole("button", { name: "검증" }));
  expect(await screen.findByText("3개 중 1개 통과")).toBeTruthy();
  expect(screen.getAllByText("실패")).toHaveLength(2);
  expect(screen.getByText("3 packets transmitted, 0 received, 100% packet loss")).toBeTruthy();
  expect(screen.getByText("10.3.4.10으로 가는 경로가 없습니다")).toBeTruthy();
  expect(screen.getByText("검사가 가리키는 주소가 의도한 인터페이스에만 있다")).toBeTruthy(); // 주소 유일성 자동 검사

  const row = screen.getByText("R1이 LAN2로 갈 때 직접 넣은 경로를 쓴다").closest("li")!;
  await user.click(within(row).getByRole("button", { name: "힌트 0/2" }));
  expect(await within(row).findByText("라우터는 직접 연결된 대역만 압니다.")).toBeTruthy();
  expect(within(row).getByRole("button", { name: "힌트 1/2" })).toBeTruthy();
  expect(calls.find((c) => c.route === "POST /lab-runs/3/hints")?.body).toEqual({ check_id: "r1-route" });
});

test("어려움은 검사별 결과 대신 통과 개수만 보여 주고 힌트 버튼이 없다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, {
      ...RUN, level: "hard", hint_limit: 0, checks: [], attempts: 1, last_attempt: { ...ATTEMPT, results: [] },
    }],
    "GET /labs": () => [200, LAB_LIST],
  });
  openLabs();

  expect(await screen.findByText("3개 중 1개 통과")).toBeTruthy();
  expect(screen.getByText(/어려움에서는 검사 목록과 검사별 결과를 끝낼 때 보여 줍니다/)).toBeTruthy();
  expect(screen.queryByRole("button", { name: /힌트/ })).toBeNull();
  expect(screen.queryByText("PC1 → PC2 ping")).toBeNull();
});

test("끝내기는 확인을 받고, 끝난 뒤 결과와 목록으로 돌아갈 버튼을 보여 준다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, RUN],
    "GET /labs": () => [200, LAB_LIST],
    "POST /lab-runs/3/finish": () => [200, FINISHED],
  });
  const user = userEvent.setup();
  openLabs();

  await user.click(await screen.findByRole("button", { name: "끝내기" }));
  const dialog = await screen.findByRole("dialog", { name: "실습을 끝낼까요?" });
  expect(dialog.textContent).toContain("실습 환경이 지워집니다. 마지막 설정은 기록에 남습니다.");
  expect(dialog.textContent).toContain("포기로 기록됩니다");
  await user.click(within(dialog).getByRole("button", { name: "끝내기" }));

  expect(await screen.findByText("실습을 끝냈습니다")).toBeTruthy();
  expect(screen.getByText("포기")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "검증" })).toBeNull();
  expect(screen.queryByText("노드 접속")).toBeNull(); // 환경이 없으니 접속 명령도 없다
  expect(count(calls, "POST /lab-runs/3/finish")).toBe(1);

  await user.click(screen.getByRole("button", { name: "목록으로" }));
  expect(await screen.findByRole("heading", { name: "실습" })).toBeTruthy();
});

test("처음부터 다시는 지금 실행을 끝내고 같은 도움 수준으로 새로 시작한다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, { ...RUN, level: "easy", hint_limit: 3 }],
    "GET /labs": () => [200, LAB_LIST],
    "POST /lab-runs/3/finish": () => [200, FINISHED],
    "POST /labs/LAB-002/runs": () => [201, { ...RUN, run_id: 4, level: "easy", networks: { ...RUN.networks, lan2: "10.9.9.0/24" } }],
  });
  const user = userEvent.setup();
  openLabs();

  await user.click(await screen.findByRole("button", { name: "처음부터 다시" }));
  const dialog = await screen.findByRole("dialog", { name: "처음부터 다시 할까요?" });
  expect(dialog.textContent).toContain("주소 대역이 새로 정해지고");
  await user.click(within(dialog).getByRole("button", { name: "다시 시작" }));

  expect(await screen.findByText("10.9.9.0/24")).toBeTruthy();
  const order = calls.map((c) => c.route).filter((r) => r.startsWith("POST"));
  expect(order).toEqual(["POST /lab-runs/3/finish", "POST /labs/LAB-002/runs"]);
  expect(calls.find((c) => c.route === "POST /labs/LAB-002/runs")?.body).toEqual({ level: "easy" });
});

test("답안 평가의 추천 실습에서 실습 열기를 누르면 그 실습의 시작 창이 열린다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, [CARD]],
    "POST /cards/7/questions/original": () => [201, ORIGINAL],
    "POST /questions/3/answers": () => [201, EVALUATION],
    "GET /lab-runs/current": () => [200, null],
    "GET /labs": () => [200, LAB_LIST],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("button", { name: CARD.question }));
  await user.type(screen.getByLabelText("내 답안"), "답안");
  await user.click(screen.getByRole("button", { name: "답안 제출" }));
  await user.click(await screen.findByRole("link", { name: "실습 열기" }));

  expect(await screen.findByRole("dialog", { name: "LAB-002 시작" })).toBeTruthy();
  expect(window.location.search).toBe(""); // 새로고침해도 시작 창을 또 열지 않는다
});

test("진행 중인 실습이 있으면 추천 실습을 바로 시작하지 않고 알린다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, RUN],
    "GET /labs": () => [200, LAB_LIST],
  });
  openLabs("/labs?start=LAB-001");

  expect(await screen.findByText(/진행 중인 실습이 있어 추천 실습 LAB-001을\(를\) 바로 시작하지 않았습니다/)).toBeTruthy();
  expect(screen.getByRole("heading", { name: RUN.title })).toBeTruthy();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("터미널은 노드 버튼이나 토폴로지 노드를 눌러 열고, 탭으로 오가며 닫을 수 있다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /lab-runs/current": () => [200, RUN],
    "GET /labs": () => [200, LAB_LIST],
  });
  const user = userEvent.setup();
  openLabs();

  const openers = await screen.findByRole("group", { name: "터미널 열기" });
  expect(within(openers).getAllByRole("button").map((b) => b.textContent)).toEqual(["pc1", "r1", "r1 (sh)", "r2", "r2 (sh)"]);
  await user.click(within(openers).getByRole("button", { name: "pc1" }));
  expect(await screen.findByText("터미널 pc1 sh (보는 중)")).toBeTruthy();

  await user.click(screen.getByRole("button", { name: "r1 터미널 열기" })); // 토폴로지 그림의 노드
  expect(await screen.findByText("터미널 r1 vtysh (보는 중)")).toBeTruthy();
  expect(screen.getByText("터미널 pc1 sh").closest("[hidden]")).toBeTruthy(); // 연결은 유지하고 숨긴다

  await user.click(within(openers).getByRole("button", { name: "r1" })); // 이미 연 터미널은 새로 열지 않는다
  expect(screen.getAllByText(/^터미널 r1 vtysh/)).toHaveLength(1);

  await user.click(screen.getByRole("button", { name: "r1 터미널 닫기" }));
  expect(screen.queryByText(/^터미널 r1/)).toBeNull();
  expect(screen.getByText("터미널 pc1 sh (보는 중)")).toBeTruthy();
});

// ---- 개념 보기 ----

const CONCEPT_BASE = {
  difficulty: null, source_type: "notion", source_ref: "41fd0d99", archived: false,
  prerequisites: [], related: [], labs: [],
};
const CONCEPTS = [
  { ...CONCEPT_BASE, id: "NET-105", title: "IP 주소와 서브넷", category: "네트워크 기본", keywords: ["CIDR"],
    card_count: 7, next_due_at: "2026-11-01T09:00:00+09:00" },
  { ...CONCEPT_BASE, id: "NET-111", title: "정적 라우팅", category: "라우팅", keywords: ["next-hop"], difficulty: 3,
    prerequisites: ["NET-105"], card_count: 7, next_due_at: "2099-01-01T09:00:00+09:00" },
];
const NET_111 = {
  ...CONCEPTS[1],
  content: "## 2. 정적 경로의 구성\n\n| 형태 | 예시 |\n| --- | --- |\n| 다음 홉 | `ip route 192.168.3.0/24 10.0.12.2` |\n\n<b>굵게</b>\n",
  questions: [],
};
const NET_111_HISTORY = {
  concept_id: "NET-111",
  cards: [{
    card_id: 21, question: "정적 경로의 기본 관리 거리는?", due_at: "2099-01-01T09:00:00+09:00", reviews: 2, last_rating: 3,
    last_reviewed_at: "2026-11-26T10:00:00+09:00", last_score: 80, last_scored_at: "2026-11-26T10:00:00+09:00",
  }],
  labs: [
    { scenario_id: "LAB-002", title: "라우터 두 대 너머로 통신하기", runs: [{
      run_id: 5, status: "passed", level: "normal", attempts: 2, attempts_to_pass: 2, hints_used: 1,
      started_at: "2026-11-26T13:00:00+09:00", passed_at: "2026-11-26T13:12:00+09:00", finished_at: "2026-11-26T13:13:00+09:00",
    }] },
    { scenario_id: "LAB-009", title: null, runs: [] },
  ],
};

test("개념 목록은 제목·키워드·id로 찾고 카테고리로 거르며, 보관된 개념은 골라서 본다", async () => {
  const calls = mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts": () => [200, CONCEPTS],
    "GET /concepts?include_archived=true": () => [200, [...CONCEPTS, { ...CONCEPTS[0], id: "NET-099", title: "옛 개념", archived: true }]],
  });
  const user = userEvent.setup();
  render(<App />);

  await user.click(screen.getByRole("link", { name: "개념" }));
  const list = await screen.findByRole("list", { name: "개념 목록" });
  expect(within(list).getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["/concepts/NET-105", "/concepts/NET-111"]);
  expect(within(list).getByText("지금 복습할 때")).toBeTruthy();

  await user.type(screen.getByRole("searchbox", { name: "개념 찾기" }), "next-hop"); // 키워드
  expect(within(screen.getByRole("list", { name: "개념 목록" })).getAllByRole("link")).toHaveLength(1);
  await user.clear(screen.getByRole("searchbox", { name: "개념 찾기" }));
  await user.click(within(screen.getByRole("group", { name: "카테고리" })).getByRole("button", { name: /네트워크 기본/ }));
  expect(within(screen.getByRole("list", { name: "개념 목록" })).getByText("IP 주소와 서브넷")).toBeTruthy();
  expect(window.location.search).toContain("category="); // 뒤로 가기로 돌아와도 남는다

  await user.click(screen.getByRole("checkbox", { name: "보관된 개념도 보기" }));
  expect(await screen.findByText("보관됨")).toBeTruthy();
  expect(count(calls, "GET /concepts?include_archived=true")).toBe(1);
});

test("개념 상세는 카드 기록·연결된 실습·본문을 보여 주고, 선수 개념으로 이동한다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts/NET-111": () => [200, NET_111],
    "GET /concepts/NET-111/history": () => [200, NET_111_HISTORY],
    "GET /concepts/NET-111/source": () => [200, {
      source_type: "notion", path: null, url: "https://www.notion.so/fe8d", text: "## 2. 정적 경로의 구성\n| 형태 | 예시 |\n<b>굵게</b>\n",
    }],
    "GET /concepts/NET-105": () => [200, { ...CONCEPTS[0], content: "서브넷 본문", questions: [] }],
    "GET /concepts/NET-105/history": () => [200, { concept_id: "NET-105", cards: [], labs: [] }],
  });
  const user = userEvent.setup();
  window.history.pushState(null, "", "/concepts/NET-111");
  render(<App />);

  expect(await screen.findByRole("heading", { level: 1, name: "정적 라우팅" })).toBeTruthy();
  const row = screen.getByText("정적 경로의 기본 관리 거리는?").closest("tr")!;
  expect([...row.querySelectorAll("td")].slice(1, 4).map((td) => td.textContent)).toEqual(["2번", "Good", "80점"]);
  expect(screen.getByText(/보통 · 2번째 검증에 통과 · 힌트 1번 · 12분 걸림/)).toBeTruthy();
  expect(screen.getByRole("link", { name: "실습 열기" }).getAttribute("href")).toBe("/labs?start=LAB-002");
  expect(screen.getByText("시나리오 파일이 없습니다")).toBeTruthy(); // 원본이 가리키지만 시나리오가 없는 실습
  expect((await screen.findByText("ip route 192.168.3.0/24 10.0.12.2")).tagName).toBe("CODE"); // 본문은 따로 불러온다
  expect(screen.getAllByRole("table")).toHaveLength(2); // 카드 표 + 본문의 Markdown 표
  expect(document.querySelector("b")).toBeNull(); // 본문의 HTML은 그리지 않는다

  await user.click(screen.getByRole("button", { name: "원본" })); // 원본은 렌더링하지 않고 그대로
  const source = await screen.findByLabelText("원본");
  expect(source.textContent).toBe("## 2. 정적 경로의 구성\n| 형태 | 예시 |\n<b>굵게</b>\n");
  expect(screen.getByRole("link", { name: /Notion에서 열기/ }).getAttribute("href")).toBe("https://www.notion.so/fe8d");
  await user.click(screen.getByRole("button", { name: "본문" }));
  expect(await screen.findByText("ip route 192.168.3.0/24 10.0.12.2")).toBeTruthy();

  await user.click(screen.getByRole("link", { name: "NET-105" }));
  expect(await screen.findByRole("heading", { level: 1, name: "IP 주소와 서브넷" })).toBeTruthy();
  expect(screen.getByText("연결된 실습이 없습니다", { exact: false })).toBeTruthy();
});

test("없는 개념은 알린다", async () => {
  mockApi({
    "GET /reviews/due": () => [200, []],
    "GET /concepts/NET-404": () => [404, { detail: "개념이 없습니다" }],
    "GET /concepts/NET-404/history": () => [404, { detail: "개념이 없습니다" }],
  });
  window.history.pushState(null, "", "/concepts/NET-404");
  render(<App />);
  expect(await screen.findByText("개념 NET-404이(가) 없습니다.")).toBeTruthy();
});

const day = (n: number) => `2026-${n > 30 ? "12" : "11"}-${String(n > 30 ? n - 30 : n).padStart(2, "0")}`;
const SUMMARY = {
  today: { due: 2, overdue: 1, reviewed: 3, concepts: 2, cards: 5, streak_days: 4 },
  reviews_by_day: Array.from({ length: 28 }, (_, i) => ({ date: day(i + 1), again: 0, hard: 0, good: i === 20 ? 2 : 0, easy: 0 }))
    .map((d, i) => (i === 27 ? { ...d, again: 1, hard: 1, good: 1 } : d)),
  due_by_day: [2, 0, 1, 0, 0, 0, 0].map((cards, i) => ({ date: day(28 + i), cards })),
  errors_by_week: [
    { start: day(1), end: day(7), reviews: 0, wrong: 0 },
    { start: day(8), end: day(14), reviews: 0, wrong: 0 },
    { start: day(15), end: day(21), reviews: 2, wrong: 0 },
    { start: day(22), end: day(28), reviews: 4, wrong: 1 },
  ],
  stages: { new: 2, learning: 1, review: 1, mature: 1 },
  categories: [
    { category: "라우팅", stages: { new: 1, learning: 1, review: 0, mature: 1 }, reviews: 4, wrong: 1 },
    { category: "네트워크 기본", stages: { new: 1, learning: 0, review: 1, mature: 0 }, reviews: 2, wrong: 2 },
  ],
  weak_concepts: [
    {
      concept_id: "NET-010", title: "Static Routing", category: "라우팅", signals: ["forgot"], again: 2, hard: 0, low_scores: 0,
      last_reviewed_at: "2026-11-28T00:20:00+09:00", next_due_at: "2026-11-16T09:00:00+09:00",
      lapses: [
        { question: "정적 라우팅이란?", rating: 1, reviewed_at: "2026-11-28T00:20:00+09:00" },
        { question: "다음 홉이란?", rating: 1, reviewed_at: "2026-11-20T21:00:00+09:00" },
      ],
      low_evaluations: [],
    },
    {
      concept_id: "NET-005", title: "IP 주소", category: "네트워크 기본", signals: ["low_score"], again: 0, hard: 0, low_scores: 2,
      last_reviewed_at: null, next_due_at: "2026-12-03T09:00:00+09:00", lapses: [],
      low_evaluations: [
        { question: "서브넷이란?", score: 40, submitted_at: "2026-11-26T10:00:00+09:00", missing_points: ["브로드캐스트 주소"] },
        { question: "서브넷이란?", score: 55, submitted_at: "2026-11-20T10:00:00+09:00", missing_points: [] },
      ],
    },
  ],
  rules: { recent_days: 30, forgot: 2, struggled: 3, low_score: 60, low_score_count: 2, mature_days: 21 },
  labs: [
    {
      scenario_id: "LAB-001", title: "대역의 첫 주소와 마지막 주소로 통신하기", runs: 2,
      last_run: {
        run_id: 3, status: "passed", level: "normal", attempts: 2, attempts_to_pass: 2, hints_used: 0,
        started_at: "2026-11-27T10:00:00+09:00", passed_at: "2026-11-27T10:12:00+09:00", finished_at: "2026-11-27T10:13:00+09:00",
      },
    },
    { scenario_id: "LAB-002", title: "정적 라우팅", runs: 0, last_run: null },
  ],
};
const ROUTING_DUE = [{ ...CARD, category: "라우팅" }, { ...CARD2, category: "라우팅" }];

test("대시보드는 사이드바로 열고, 지표·차트·취약 개념·실습 이력을 보여 준다", async () => {
  mockApi({ "GET /reviews/due": () => [200, ROUTING_DUE], "GET /dashboard/summary": () => [200, SUMMARY] });
  const user = userEvent.setup();
  render(<App />);

  await user.click(await screen.findByRole("link", { name: "대시보드" }));
  expect(await screen.findByText("밀린 복습 1장")).toBeTruthy();
  expect(screen.getByRole("heading", { level: 1, name: "대시보드" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "학습 시작 · 2장" })).toBeTruthy();

  // 차트의 칸마다 값을 접근성 이름으로 갖고, 같은 값을 표로도 볼 수 있다
  expect(screen.getByLabelText("11월 28일 (토) 복습 3번: Again 1, Hard 1, Good 1, Easy 0")).toBeTruthy();
  expect(screen.getByLabelText("11월 28일 (토) 복습 예정 2장")).toBeTruthy();
  expect(screen.getByLabelText("최근 7일 오답률 25% (4번 중 1번)")).toBeTruthy();
  expect(screen.getByLabelText("11/1~11/7 복습 기록 없음")).toBeTruthy();
  expect(screen.getByLabelText("전체 5장: 익숙함 1, 복습 중 1, 학습 중 1, 새 카드 2")).toBeTruthy();
  expect(screen.getAllByText("표로 보기")).toHaveLength(4); // 카테고리별 오답률은 줄마다 값을 글자로 쓴다

  // 카테고리별 오답률은 높은 순 (Again·Hard 비율)
  const rates = within(screen.getByRole("region", { name: "카테고리별 오답률" })).getAllByLabelText(/오답률/);
  expect(rates.map((m) => m.getAttribute("aria-label"))).toEqual(["네트워크 기본 오답률 100% (2번 중 2번)", "라우팅 오답률 25% (4번 중 1번)"]);

  const weak = within(screen.getByRole("list", { name: "취약 개념 목록" }));
  expect(weak.getByText("잊음 · Again 2회")).toBeTruthy();
  expect(weak.getByText("낮은 평가 · 2회")).toBeTruthy();
  expect(weak.getByRole("button", { name: "Static Routing 복습 시작 (2장)" })).toBeTruthy();
  expect(weak.getByText("다음 복습 12월 3일")).toBeTruthy(); // 지금 복습할 카드가 없는 개념
  expect(weak.getByText("빠진 내용: 브로드캐스트 주소")).toBeTruthy();
  expect(weak.getByRole("link", { name: "IP 주소" }).getAttribute("href")).toBe("/concepts/NET-005");

  const labs = within(screen.getByRole("list", { name: "실습 이력" }));
  expect(labs.getByText("2번째 검증에 통과 · 12분 걸림")).toBeTruthy();
  expect(labs.getByText("아직 해 보지 않았습니다")).toBeTruthy();
  expect(labs.getAllByRole("link", { name: /실습 열기/ }).map((a) => a.getAttribute("href"))).toEqual(["/labs?start=LAB-001", "/labs?start=LAB-002"]);
});

test("대시보드에서 전체·카테고리·취약 개념의 학습을 바로 시작하고, 마치면 대시보드로 돌아온다", async () => {
  const basics = { ...CARD, card_id: 9, concept_id: "NET-005", concept_title: "IP 주소", category: "네트워크 기본", question: "서브넷이란?" };
  const calls = mockApi({ "GET /reviews/due": () => [200, [...ROUTING_DUE, basics]], "GET /dashboard/summary": () => [200, SUMMARY] });
  const user = userEvent.setup();
  window.history.pushState(null, "", "/dashboard");
  render(<App />);

  await user.click(await screen.findByRole("button", { name: "학습 시작 · 3장" }));
  expect(screen.getByRole("heading", { name: CARD.question })).toBeTruthy();
  expect(screen.getByText("1 / 3")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "목록" }));
  expect(await screen.findByRole("heading", { level: 1, name: "대시보드" })).toBeTruthy();
  expect(window.location.pathname).toBe("/dashboard");

  const stages = await screen.findByLabelText("전체 5장: 익숙함 1, 복습 중 1, 학습 중 1, 새 카드 2");
  await user.click(within(stages.closest("ul")!).getByRole("button", { name: "네트워크 기본 복습 시작 (1장)" }));
  expect(screen.getByRole("heading", { name: "서브넷이란?" })).toBeTruthy();
  expect(screen.getByText("1 / 1")).toBeTruthy();
  await user.click(screen.getByRole("button", { name: "목록" }));

  await user.click(await screen.findByRole("button", { name: "Static Routing 복습 시작 (2장)" }));
  expect(screen.getByText("1 / 2")).toBeTruthy();
  expect(count(calls, "GET /dashboard/summary")).toBe(3); // 돌아올 때마다 새로 계산한다
});

test("기록이 없으면 대시보드는 빈 상태를 알리고 시작 버튼을 막는다", async () => {
  const empty = {
    ...SUMMARY,
    today: { due: 0, overdue: 0, reviewed: 0, concepts: 1, cards: 3, streak_days: 0 },
    reviews_by_day: SUMMARY.reviews_by_day.map((d) => ({ ...d, again: 0, hard: 0, good: 0, easy: 0 })),
    due_by_day: SUMMARY.due_by_day.map((d) => ({ ...d, cards: 0 })),
    errors_by_week: SUMMARY.errors_by_week.map((w) => ({ ...w, reviews: 0, wrong: 0 })),
    stages: { new: 3, learning: 0, review: 0, mature: 0 },
    categories: [{ category: null, stages: { new: 3, learning: 0, review: 0, mature: 0 }, reviews: 0, wrong: 0 }],
    weak_concepts: [],
    labs: [],
  };
  mockApi({ "GET /reviews/due": () => [200, []], "GET /dashboard/summary": () => [200, empty] });
  window.history.pushState(null, "", "/dashboard");
  render(<App />);

  expect(await screen.findAllByText("최근 4주 동안 복습 기록이 없습니다.")).toHaveLength(2); // 복습량·오답률
  expect(screen.getByText("앞으로 7일 동안 복습할 카드가 없습니다.")).toBeTruthy();
  expect(screen.getByText("기준에 걸린 개념이 없습니다.")).toBeTruthy();
  expect(screen.getByText("밀린 복습 없음")).toBeTruthy();
  expect(screen.queryByRole("button", { name: /학습 시작/ })).toBeNull();
  const none = screen.getAllByRole("button", { name: /지금 복습할 카드 없음/ });
  expect(none.map((b) => b.getAttribute("aria-label"))).toEqual(["분류 없음 지금 복습할 카드 없음", "전체 지금 복습할 카드 없음", "분류 없음 지금 복습할 카드 없음"]);
  expect(none.every((b) => (b as HTMLButtonElement).disabled)).toBe(true);
});
