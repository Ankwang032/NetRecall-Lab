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
