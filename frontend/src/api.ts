// 백엔드 API 응답 타입. backend/api/*.py의 pydantic 모델과 맞춘다.

export type SyncResponse = {
  dry_run: boolean;
  summary: Record<string, number>;
  errors: { source_ref: string; message: string }[];
  dangling_refs: { concept_id: string; ref: string }[];
};

export type DueCard = {
  card_id: number;
  concept_id: string;
  concept_title: string;
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

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    // HTTPException은 detail이 문자열, 422 검증 오류는 목록이다
    throw new Error(typeof data?.detail === "string" ? data.detail : `요청 실패 (${res.status})`);
  }
  return data as T;
}

export function errorMessage(e: unknown) {
  return e instanceof Error ? e.message : String(e);
}

export const api = {
  sync: () => request<SyncResponse>("POST", "/sync/markdown"),
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
};
