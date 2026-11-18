import { useEffect, useId, useState } from "react";
import {
  CheckCircleIcon, FileTextIcon, FloppyDiskIcon, SpinnerIcon, UploadSimpleIcon, WarningCircleIcon, XCircleIcon, XIcon,
} from "@phosphor-icons/react";
import { toast } from "sonner";
import { api, errorMessage, type FileCheck, type UploadFile } from "@/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

const ROOT = "/"; // Radix Select는 빈 문자열 값을 쓸 수 없어 개념 폴더 최상위("")를 이 값으로 나타낸다

type Props = { open: boolean; onOpenChange: (open: boolean) => void; onSaved: () => void };

// .md 개념 파일을 올린다. 고르는 즉시 검사(dry run)하고, 모두 통과해야 저장할 수 있다
export function UploadDialog({ open, onOpenChange, onSaved }: Props) {
  const [folders, setFolders] = useState<string[]>([""]);
  const [folder, setFolder] = useState("");
  const [files, setFiles] = useState<UploadFile[]>([]);
  const [checks, setChecks] = useState<FileCheck[] | null>(null);
  const [checking, setChecking] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputId = useId();

  useEffect(() => {
    if (!open) {
      setFiles([]);
      setChecks(null);
      setError(null);
      return;
    }
    api.folders().then(setFolders).catch((e) => setError(errorMessage(e)));
  }, [open]);

  useEffect(() => {
    setChecks(null);
    if (files.length === 0) return;
    let stale = false;
    setChecking(true);
    setError(null);
    api
      .checkFiles(folder, files)
      .then((r) => !stale && setChecks(r.files))
      .catch((e) => !stale && setError(errorMessage(e)))
      .finally(() => !stale && setChecking(false));
    return () => {
      stale = true;
    };
  }, [files, folder]);

  async function addFiles(list: FileList) {
    const added = await Promise.all(
      [...list].map(async (f) => ({ name: f.name, content: await f.text() })),
    );
    // 같은 이름을 다시 고르면 새 내용으로 바꾼다
    setFiles((prev) => [...prev.filter((p) => !added.some((a) => a.name === p.name)), ...added]);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveFiles(folder, files);
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

  const allPassed = checks !== null && checks.length === files.length && checks.every((c) => c.errors.length === 0);
  const canSave = files.length > 0 && allPassed && !checking && !saving;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>개념 파일 추가</DialogTitle>
          <DialogDescription>
            Markdown 개념 파일을 형식 검사한 뒤 개념 폴더에 저장하고 바로 동기화합니다.
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
            addFiles(e.dataTransfer.files);
          }}
          className={cn(
            "flex cursor-pointer flex-col items-center gap-1.5 rounded-xl border-2 border-dashed px-6 py-7 text-center transition-colors focus-within:ring-3 focus-within:ring-ring/50",
            dragging ? "border-primary bg-accent" : "border-input hover:border-primary/60 hover:bg-muted/50",
          )}
        >
          <UploadSimpleIcon className="mb-1 size-8 text-primary" aria-hidden />
          <span className="font-medium">.md 파일을 끌어다 놓거나 눌러서 고르세요</span>
          <span className="text-xs text-muted-foreground">
            여러 개 가능 · frontmatter에 id, 본문, ## 질문 아래 질문 3개 이상
          </span>
          <input
            id={inputId}
            type="file"
            accept=".md,text/markdown"
            multiple
            className="sr-only"
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = ""; // 같은 파일을 다시 고를 수 있게
            }}
          />
        </label>

        {files.length > 0 && (
          <ul className="max-h-64 divide-y overflow-y-auto rounded-lg border" aria-label="올릴 파일">
            {files.map((f) => (
              <FileRow
                key={f.name}
                name={f.name}
                check={checking ? undefined : checks?.find((c) => c.name === f.name)}
                onRemove={() => setFiles((prev) => prev.filter((p) => p.name !== f.name))}
              />
            ))}
          </ul>
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
          <Button onClick={save} disabled={!canSave}>
            {saving ? <SpinnerIcon className="animate-spin" aria-hidden /> : <FloppyDiskIcon aria-hidden />}
            {files.length > 0 ? `${files.length}개 저장` : "저장"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function FileRow({ name, check, onRemove }: { name: string; check?: FileCheck; onRemove: () => void }) {
  return (
    <li className="flex items-start gap-3 px-3 py-2.5">
      <FileTextIcon className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-medium [overflow-wrap:anywhere]">{name}</p>
        {!check ? (
          <p className="flex items-center gap-1.5 text-muted-foreground">
            <SpinnerIcon className="size-3.5 animate-spin" aria-hidden /> 검사하는 중…
          </p>
        ) : check.errors.length === 0 ? (
          <p className="flex items-center gap-1.5 text-success">
            <CheckCircleIcon weight="fill" className="size-3.5 shrink-0" aria-hidden />
            <span>
              통과 · {check.concept_id} {check.title} · 질문 {check.question_count}개 →{" "}
              <span className="font-mono">{check.path}</span>
            </span>
          </p>
        ) : (
          <ul className="space-y-0.5 text-destructive">
            {check.errors.map((e, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <XCircleIcon weight="fill" className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                {e}
              </li>
            ))}
          </ul>
        )}
      </div>
      <Button variant="ghost" size="icon-sm" onClick={onRemove} aria-label={`${name} 빼기`}>
        <XIcon aria-hidden />
      </Button>
    </li>
  );
}
