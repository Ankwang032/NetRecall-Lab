import { useEffect, useId, useRef, useState } from "react";
import {
  CheckCircleIcon, FileTextIcon, FloppyDiskIcon, MagicWandIcon, SpinnerIcon, UploadSimpleIcon, WarningCircleIcon,
  WarningIcon, XCircleIcon, XIcon,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { api, errorMessage, type FileCheck, type NotionFile, type PlannedFile, type UploadFile } from "@/api";
import { NotionPicker } from "@/components/NotionPicker";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";

const ROOT = "/"; // Radix Select는 빈 문자열 값을 쓸 수 없어 개념 폴더 최상위("")를 이 값으로 나타낸다

type Props = { open: boolean; onOpenChange: (open: boolean) => void; onSaved: () => void };

// 올릴 파일 하나. 형식 맞추기 계획(plan) → 필요하면 AI 변환 → 검사(check) → 저장 순서로 진행한다
type Item = {
  name: string;
  content: string; // 변환하면 표준 형식 내용으로 바뀐다
  plan: PlannedFile | null; // null = 계획 전
  converted: boolean;
  converting: boolean;
  convertError: string | null;
  warnings: string[]; // Notion 가져오기·AI 변환 경고
};

const newItem = (name: string, content: string, warnings: string[] = []): Item => ({
  name, content, plan: null, converted: false, converting: false, convertError: null, warnings,
});

const needsConvert = (i: Item) => i.plan?.status === "convert" && !i.converted;
const isReady = (i: Item) => i.plan?.status === "standard" || i.converted;

// .md 파일이나 Notion 페이지를 개념으로 추가한다. 형식이 다르면 AI로 표준 형식을 맞추고,
// 검사를 모두 통과해야 저장할 수 있다
export function UploadDialog({ open, onOpenChange, onSaved }: Props) {
  const [folders, setFolders] = useState<string[]>([""]);
  const [folder, setFolder] = useState("");
  const [items, setItems] = useState<Item[]>([]);
  const [planning, setPlanning] = useState(false);
  const [converting, setConverting] = useState(false);
  const [checks, setChecks] = useState<FileCheck[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const planSeq = useRef(0);
  const inputId = useId();

  useEffect(() => {
    if (!open) {
      planSeq.current++;
      setItems([]);
      setChecks(null);
      setError(null);
      return;
    }
    api.folders().then(setFolders).catch((e) => setError(errorMessage(e)));
  }, [open]);

  // 모든 파일이 표준 형식이 되면 저장 전 검사를 한다
  const allReady = items.length > 0 && items.every(isReady);
  const readyKey = allReady ? JSON.stringify([folder, items.map((i) => [i.name, i.content])]) : null;
  useEffect(() => {
    setChecks(null);
    if (readyKey === null) return;
    let stale = false;
    setChecking(true);
    setError(null);
    api
      .checkFiles(folder, items.map(({ name, content }) => ({ name, content })))
      .then((r) => !stale && setChecks(r.files))
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setChecking(false));
    return () => {
      stale = true;
    };
  }, [readyKey]); // readyKey가 folder와 모든 파일 내용을 담는다

  // 파일을 더하거나 빼면 id가 달라질 수 있어 전체를 다시 계획한다
  async function replan(next: Item[]) {
    const seq = ++planSeq.current;
    setItems(next.map((i) => ({ ...i, plan: null })));
    if (next.length === 0) return;
    setPlanning(true);
    setError(null);
    try {
      const { files } = await api.planNormalize(next.map(({ name, content }) => ({ name, content })));
      if (seq !== planSeq.current) return;
      setItems(next.map((i) => ({ ...i, plan: files.find((p) => p.name === i.name) ?? null })));
    } catch (e) {
      if (seq === planSeq.current) setError(errorMessage(e));
    } finally {
      if (seq === planSeq.current) setPlanning(false);
    }
  }

  // 같은 이름을 다시 고르면 새 내용으로 바꾼다
  function add(added: Item[]) {
    replan([...items.filter((i) => !added.some((a) => a.name === i.name)), ...added]);
  }

  async function addFiles(list: FileList) {
    add(await Promise.all([...list].map(async (f) => newItem(f.name, await f.text()))));
  }

  function addNotion(files: NotionFile[]) {
    add(files.map((f) => newItem(f.name, f.content ?? "", f.warnings)));
  }

  function update(name: string, patch: Partial<Item>) {
    setItems((prev) => prev.map((i) => (i.name === name ? { ...i, ...patch } : i)));
  }

  // 파일 하나에 AI 호출 1번. 실패하면 멈추고, 다시 누르면 남은 파일부터 한다
  async function convertAll() {
    setConverting(true);
    setError(null);
    const batch = items.flatMap((i) =>
      i.plan?.concept_id && i.plan.title ? [{ concept_id: i.plan.concept_id, title: i.plan.title }] : [],
    );
    for (const item of items.filter(needsConvert)) {
      const plan = item.plan!;
      update(item.name, { converting: true, convertError: null });
      try {
        const r = await api.convertFile(
          { name: item.name, content: item.content },
          plan.concept_id!,
          batch.filter((b) => b.concept_id !== plan.concept_id),
        );
        update(item.name, {
          content: r.content, converted: true, converting: false,
          plan: { ...plan, title: r.title }, warnings: [...item.warnings, ...r.warnings],
        });
      } catch (e) {
        update(item.name, { converting: false, convertError: errorMessage(e) });
        break;
      }
    }
    setConverting(false);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveFiles(folder, items.map(({ name, content }) => ({ name, content })));
      if (!result.saved) {
        setChecks(result.files); // 검사 뒤에 폴더가 바뀐 경우
        return;
      }
      const cards = result.files.reduce((n, f) => n + f.question_count, 0);
      toast.success(`개념 ${result.files.length}개를 추가했습니다`, {
        description: `복습할 카드 ${cards}장이 생겼습니다`,
      });
      onSaved();
      onOpenChange(false);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  const toConvert = items.filter(needsConvert);
  const doneCount = items.filter((i) => i.converted).length;
  const busy = planning || converting || saving;
  const allPassed = checks !== null && checks.length === items.length && checks.every((c) => c.errors.length === 0);
  const canSave = allReady && allPassed && !checking && !busy;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>개념 추가</DialogTitle>
          <DialogDescription>
            Markdown 파일이나 Notion 페이지를 가져옵니다. 형식이 다르면 AI가 표준 개념 형식으로 맞춥니다.
            검사를 통과하면 개념 폴더에 저장하고 바로 동기화합니다.
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-2">
          <Label htmlFor={`${inputId}-folder`}>저장할 폴더</Label>
          <Select value={folder || ROOT} onValueChange={(v) => setFolder(v === ROOT ? "" : v)}>
            <SelectTrigger id={`${inputId}-folder`} className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {folders.map((f) => (
                <SelectItem key={f || ROOT} value={f || ROOT}>
                  {f ? `${f}/` : "개념 폴더 최상위"}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Tabs defaultValue="files">
          <TabsList className="w-full">
            <TabsTrigger value="files">파일 올리기</TabsTrigger>
            <TabsTrigger value="notion">Notion에서 가져오기</TabsTrigger>
          </TabsList>
          <TabsContent value="files">
            <label
              htmlFor={inputId}
              onDragOver={(e) => {
                e.preventDefault();
                setDragging(true);
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                if (!busy) addFiles(e.dataTransfer.files);
              }}
              className={cn(
                "flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border-2 border-dashed px-6 py-7 text-center transition-colors focus-within:ring-3 focus-within:ring-ring/50",
                dragging ? "border-primary bg-accent" : "border-input hover:border-primary/60 hover:bg-muted/50",
              )}
            >
              <UploadSimpleIcon className="mb-1 size-8 text-primary" aria-hidden />
              <span className="font-medium">.md 파일을 끌어다 놓거나 눌러서 고르세요</span>
              <span className="text-xs text-muted-foreground">
                여러 개 가능 · 표준 형식이 아니면 AI가 형식을 맞춥니다
              </span>
              <input
                id={inputId}
                type="file"
                accept=".md,text/markdown"
                multiple
                disabled={busy}
                className="sr-only"
                onChange={(e) => {
                  if (e.target.files) addFiles(e.target.files);
                  e.target.value = ""; // 같은 파일을 다시 고를 수 있게
                }}
              />
            </label>
          </TabsContent>
          <TabsContent value="notion">
            <NotionPicker disabled={busy} onAdd={addNotion} />
          </TabsContent>
        </Tabs>

        {items.length > 0 && (
          <ul className="max-h-72 divide-y overflow-y-auto rounded-lg border" aria-label="추가할 파일">
            {items.map((item) => (
              <FileRow
                key={item.name}
                item={item}
                planning={planning}
                check={checking ? undefined : checks?.find((c) => c.name === item.name)}
                disabled={busy}
                onRemove={() => replan(items.filter((i) => i.name !== item.name))}
              />
            ))}
          </ul>
        )}

        {converting && (
          <p className="text-sm text-muted-foreground" role="status">
            AI가 형식을 맞추는 중 ({doneCount + 1}/{doneCount + toConvert.length}) · 파일 하나에 20~60초쯤 걸립니다
          </p>
        )}

        {error && (
          <Alert variant="destructive">
            <WarningCircleIcon aria-hidden />
            <AlertTitle>요청을 처리하지 못했습니다</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>취소</Button>
          {toConvert.length > 0 ? (
            <Button onClick={convertAll} disabled={busy}>
              {converting ? <SpinnerIcon className="animate-spin" aria-hidden /> : <MagicWandIcon aria-hidden />}
              형식 맞추기 (AI {toConvert.length}번)
            </Button>
          ) : (
            <Button onClick={save} disabled={!canSave}>
              {saving ? <SpinnerIcon className="animate-spin" aria-hidden /> : <FloppyDiskIcon aria-hidden />}
              {items.length > 0 ? `${items.length}개 저장` : "저장"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

type RowProps = { item: Item; planning: boolean; check?: FileCheck; disabled: boolean; onRemove: () => void };

function FileRow({ item, planning, check, disabled, onRemove }: RowProps) {
  const { plan } = item;
  const warnings = [...new Set([...item.warnings, ...(plan?.warnings ?? [])])];
  return (
    <li className="flex items-start gap-3 px-3 py-2.5">
      <FileTextIcon className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1 space-y-1 text-sm">
        <p className="flex flex-wrap items-center gap-1.5 font-medium [overflow-wrap:anywhere]">
          {item.name}
          {item.converted && <Badge variant="secondary">AI로 맞춤</Badge>}
        </p>
        <RowStatus item={item} planning={planning} check={check} />
        {warnings.length > 0 && (
          <ul className="space-y-0.5 text-warning">
            {warnings.map((w, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <WarningIcon weight="fill" className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {w}
              </li>
            ))}
          </ul>
        )}
        {item.converted && (
          <details>
            <summary className="cursor-pointer text-muted-foreground hover:text-foreground">맞춘 내용 보기</summary>
            <pre className="mt-1 max-h-60 overflow-auto rounded-md bg-muted p-2 text-xs whitespace-pre-wrap">
              {item.content}
            </pre>
          </details>
        )}
      </div>
      <Button variant="ghost" size="icon-sm" onClick={onRemove} disabled={disabled} aria-label={`${item.name} 빼기`}>
        <XIcon aria-hidden />
      </Button>
    </li>
  );
}

function RowStatus({ item, planning, check }: { item: Item; planning: boolean; check?: FileCheck }) {
  const { plan } = item;
  if (!plan) {
    return planning ? <Pending>확인하는 중…</Pending> : <p className="text-muted-foreground">확인하지 못했습니다</p>;
  }
  if (plan.status === "failed") return <Errors errors={[plan.error ?? "쓸 수 없는 파일입니다"]} />;
  if (item.converting) return <Pending>AI가 형식을 맞추는 중…</Pending>;
  if (item.convertError) return <Errors errors={[`형식을 맞추지 못했습니다: ${item.convertError}`]} />;
  if (needsConvert(item)) {
    return (
      <p className="flex items-center gap-1.5 text-muted-foreground">
        <MagicWandIcon className="size-3.5 shrink-0" aria-hidden />
        형식 맞추기 필요 · {plan.concept_id} {plan.title}
      </p>
    );
  }
  if (!check) return <Pending>검사하는 중…</Pending>;
  if (check.errors.length > 0) return <Errors errors={check.errors} />;
  return (
    <p className="flex items-center gap-1.5 text-success">
      <CheckCircleIcon weight="fill" className="size-3.5 shrink-0" aria-hidden />
      <span>
        통과 · {check.concept_id} {check.title} · 질문 {check.question_count}개 →{" "}
        <span className="font-mono">{check.path}</span>
      </span>
    </p>
  );
}

function Pending({ children }: { children: React.ReactNode }) {
  return (
    <p className="flex items-center gap-1.5 text-muted-foreground">
      <SpinnerIcon className="size-3.5 animate-spin" aria-hidden /> {children}
    </p>
  );
}

function Errors({ errors }: { errors: string[] }) {
  return (
    <ul className="space-y-0.5 text-destructive">
      {errors.map((e, i) => (
        <li key={i} className="flex items-start gap-1.5">
          <XCircleIcon weight="fill" className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          {e}
        </li>
      ))}
    </ul>
  );
}
