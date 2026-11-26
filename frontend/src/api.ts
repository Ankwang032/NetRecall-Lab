// 백엔드 API 응답 타입. backend/api/*.py의 pydantic 모델과 맞춘다.

export type SyncResponse = {
  dry_run: boolean;
  summary: Record<string, number>;
  errors: { source_ref: string; message: string }[];
  warnings: { source_ref: string; message: string }[]; // 반영은 했지만 알릴 것
  dangling_refs: { concept_id: string; ref: string }[];
};

// ---- 개념 보기 (읽기 전용, 설계서 §E-2) ----

export type ConceptSummary = {
  id: string;
  title: string;
  category: string | null;
  difficulty: number | null;
  keywords: string[];
  source_type: string; // markdown | notion
  source_ref: string; // Markdown은 파일 경로, Notion은 페이지 id
  archived: boolean;
  prerequisites: string[];
  related: string[];
  labs: string[];
  card_count: number;
  next_due_at: string | null;
};

export type ConceptDetail = ConceptSummary & { content: string; questions: string[] };

export type ConceptSource = {
  source_type: string; // markdown | notion
  path: string | null; // Markdown 파일 경로 (개념 폴더 기준)
  url: string | null; // Notion 페이지 주소
  text: string; // Markdown은 파일 그대로, Notion은 가져와 저장한 본문
};

export type ConceptHistory = {
  concept_id: string;
  cards: {
    card_id: number;
    question: string;
    due_at: string;
    reviews: number;
    last_rating: number | null; // 1=Again, 2=Hard, 3=Good, 4=Easy
    last_reviewed_at: string | null;
    last_score: number | null; // 원래 질문의 최근 AI 평가 점수
    last_scored_at: string | null;
  }[];
  labs: { scenario_id: string; title: string | null; runs: LabRunSummary[] }[]; // title이 없으면 시나리오 파일이 없다
};

export type DueCard = {
  card_id: number;
  concept_id: string;
  concept_title: string;
  category: string | null;
  question: string;
  due_at: string;
};

export type Question = {
  question_id: number;
  card_id: number;
  concept_id: string;
  base_question: string;
  question: string;
  kind: "original" | "variant";
  relative_difficulty: number | null; // 변형 질문만. -2 훨씬 쉬움 ~ 2 훨씬 어려움
  difficulty_reason: string | null;
  created_at: string;
};

export type Evaluation = {
  submission_id: number;
  score: number;
  accuracy: number;
  completeness: number;
  logic: number;
  technical_validity: number;
  application: number;
  strengths: string[];
  missing_points: string[];
  technical_errors: string[];
  recommended_lab: string | null;
  model: string;
  submitted_at: string;
};

export type ReviewResult = {
  card_id: number;
  rating: number;
  reviewed_at: string;
  next_due_at: string;
};

export type UploadFile = { name: string; content: string };

export type FileCheck = {
  name: string;
  path: string; // 개념 폴더 기준 저장 경로
  concept_id: string | null;
  title: string | null;
  question_count: number;
  errors: string[];
};

export type UploadResult = {
  saved: boolean;
  files: FileCheck[];
  sync: SyncResponse | null;
};

// 형식 맞추기 1단계. standard: 그대로 저장 가능, convert: AI로 맞춰야 함, failed: 쓸 수 없음
export type PlannedFile = {
  name: string;
  status: "standard" | "convert" | "failed";
  concept_id: string | null;
  title: string | null;
  warnings: string[];
  error: string | null;
};

export type ConvertedFile = {
  name: string;
  concept_id: string;
  title: string;
  content: string; // 표준 형식 .md
  warnings: string[];
};

export type NotionPage = { page_id: string; title: string };

export type NotionPages = { parent: NotionPage; pages: NotionPage[] };

export type NotionFile = {
  page_id: string;
  title: string;
  name: string; // 제안하는 파일 이름
  content: string | null; // 실패하면 null
  warnings: string[];
  error: string | null;
};

// ---- 실습 (backend/api/labs.py) ----

export type LabLevel = "easy" | "normal" | "hard"; // 도움 수준. 힌트 3단계 / 2단계 / 힌트 없음·검사별 결과 숨김

export type LabRunSummary = {
  run_id: number;
  status: string;
  level: LabLevel;
  attempts: number;
  attempts_to_pass: number | null; // 처음 통과한 검증이 몇 번째였나
  hints_used: number;
  started_at: string;
  passed_at: string | null;
  finished_at: string | null;
};

export type LabScenario = {
  id: string;
  title: string;
  type: string;
  concepts: string[];
  time_limit_minutes: number;
  last_run: LabRunSummary | null;
};

export type LabList = { scenarios: LabScenario[]; errors: { scenario: string; message: string }[] };

export type LabResult = {
  check_id: string;
  description: string;
  kind: string; // ping | route | address | unique(주소 유일성 자동 검사)
  passed: boolean;
  message: string;
  output: string;
};

export type LabAttempt = {
  attempt_id: number;
  run_id: number;
  run_status: string;
  passed: boolean;
  attempted_at: string;
  passed_count: number;
  total_count: number;
  results: LabResult[]; // 어려움은 끝낼 때까지 비어 있다
};

// status: deploying | active | passed | abandoned | expired | deploy_failed. finished_at이 없으면 환경이 있다
export type LabRun = {
  run_id: number;
  scenario_id: string;
  title: string;
  status: string;
  goal: string;
  networks: Record<string, string>; // 대역 이름 → 이번 실행의 대역
  addresses: { interface: string; address: string }[]; // 배포할 때 넣은 주소
  nodes: { name: string; kind: string; connect: string }[];
  links: { a: string; b: string }[]; // 노드:인터페이스
  level: LabLevel;
  hint_limit: number;
  checks: { id: string; description: string }[]; // 어려움은 끝낼 때까지 비어 있다
  attempts: number;
  hints_used: number;
  hints: Record<string, string[]>; // 검사 id → 지금까지 연 힌트
  last_attempt: LabAttempt | null;
  started_at: string;
  expires_at: string;
  passed_at: string | null;
  finished_at: string | null;
  error: string | null;
};

export type LabHint = {
  check_id: string;
  number: number;
  description: string;
  hints: string[]; // 지금까지 연 힌트
  new: boolean; // 이번에 새 단계를 열었는가
  limit: number;
  total: number;
};

// HTTP 상태를 함께 담는다. 503은 그 기능이 설정되지 않았다는 뜻이다
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    // HTTPException은 detail이 문자열, 422 검증 오류는 목록이다
    throw new ApiError(typeof data?.detail === "string" ? data.detail : `요청 실패 (${res.status})`, res.status);
  }
  return data as T;
}

export function errorMessage(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

export const api = {
  sync: () => request<SyncResponse>("POST", "/sync/markdown"),
  syncNotion: () => request<SyncResponse>("POST", "/sync/notion"),
  dueCards: () => request<DueCard[]>("GET", "/reviews/due"),
  createOriginalQuestion: (cardId: number) =>
    request<Question>("POST", `/cards/${cardId}/questions/original`),
  createVariantQuestion: (cardId: number) => request<Question>("POST", `/cards/${cardId}/questions`),
  submitAnswer: (questionId: number, answer: string) =>
    request<Evaluation>("POST", `/questions/${questionId}/answers`, { answer }),
  review: (cardId: number, rating: number) =>
    request<ReviewResult>("POST", "/reviews", { card_id: cardId, rating }),
  folders: () => request<string[]>("GET", "/concepts/folders"),
  checkFiles: (folder: string, files: UploadFile[]) =>
    request<UploadResult>("POST", "/concepts/files?dry_run=true", { folder, files }),
  saveFiles: (folder: string, files: UploadFile[]) =>
    request<UploadResult>("POST", "/concepts/files", { folder, files }),
  planNormalize: (files: UploadFile[]) =>
    request<{ files: PlannedFile[] }>("POST", "/concepts/normalize/plan", { files }),
  convertFile: (file: UploadFile, conceptId: string, batch: { concept_id: string; title: string }[]) =>
    request<ConvertedFile>("POST", "/concepts/normalize/convert", { file, concept_id: conceptId, batch }),
  notionPages: (parent: string) =>
    request<NotionPages>("GET", `/notion/pages?parent=${encodeURIComponent(parent)}`),
  notionFiles: (pageIds: string[]) =>
    request<{ files: NotionFile[] }>("POST", "/notion/files", { page_ids: pageIds }),
  concepts: (includeArchived: boolean) =>
    request<ConceptSummary[]>("GET", `/concepts${includeArchived ? "?include_archived=true" : ""}`),
  concept: (id: string) => request<ConceptDetail>("GET", `/concepts/${encodeURIComponent(id)}`),
  conceptSource: (id: string) => request<ConceptSource>("GET", `/concepts/${encodeURIComponent(id)}/source`),
  conceptHistory: (id: string) => request<ConceptHistory>("GET", `/concepts/${encodeURIComponent(id)}/history`),
  labs: () => request<LabList>("GET", "/labs"),
  currentRun: () => request<LabRun | null>("GET", "/lab-runs/current"),
  labRun: (runId: number) => request<LabRun>("GET", `/lab-runs/${runId}`),
  startLab: (scenarioId: string, level: LabLevel) =>
    request<LabRun>("POST", `/labs/${encodeURIComponent(scenarioId)}/runs`, { level }),
  verifyLab: (runId: number) => request<LabAttempt>("POST", `/lab-runs/${runId}/attempts`),
  labHint: (runId: number, checkId: string) => request<LabHint>("POST", `/lab-runs/${runId}/hints`, { check_id: checkId }),
  finishLab: (runId: number) => request<LabRun>("POST", `/lab-runs/${runId}/finish`),
  terminalTicket: (runId: number, node: string, shell: string) =>
    request<{ ticket: string; node: string; shell: string }>("POST", `/lab-runs/${runId}/terminal-tickets`, { node, shell }),
};
