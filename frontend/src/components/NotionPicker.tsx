import { useId, useState } from "react";
import { DownloadSimpleIcon, MagnifyingGlassIcon, SpinnerIcon, WarningCircleIcon } from "@phosphor-icons/react";
import { api, errorMessage, type NotionFile, type NotionPage } from "@/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = { disabled: boolean; onAdd: (files: NotionFile[]) => void };

// Notion 페이지 주소를 넣으면 하위 페이지를 보여 주고, 고른 페이지를 .md 내용으로 가져온다.
// 하위 페이지가 없으면 그 페이지 자체를 가져온다
export function NotionPicker({ disabled, onAdd }: Props) {
  const [address, setAddress] = useState("");
  const [pages, setPages] = useState<NotionPage[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [failed, setFailed] = useState<NotionFile[]>([]);
  const inputId = useId();

  async function load(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setFailed([]);
    try {
      const result = await api.notionPages(address.trim());
      const list = result.pages.length > 0 ? result.pages : [result.parent];
      setPages(list);
      setSelected(new Set(list.map((p) => p.page_id)));
    } catch (err) {
      setPages(null);
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }

  async function importSelected() {
    setImporting(true);
    setError(null);
    try {
      const { files } = await api.notionFiles([...selected]);
      setFailed(files.filter((f) => f.content === null));
      onAdd(files.filter((f) => f.content !== null));
      setPages(null); // 가져온 페이지는 아래 파일 목록에 있다. 더 가져오려면 다시 불러온다
      setSelected(new Set());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setImporting(false);
    }
  }

  function toggle(pageId: string, on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (on) next.add(pageId);
      else next.delete(pageId);
      return next;
    });
  }

  return (
    <div className="grid gap-3">
      <form onSubmit={load} className="grid gap-2">
        <Label htmlFor={inputId}>Notion 페이지 주소</Label>
        <div className="flex gap-2">
          <Input
            id={inputId}
            value={address}
            onChange={(e) => setAddress(e.target.value)}
            placeholder="https://www.notion.so/..."
            autoComplete="off"
          />
          <Button type="submit" variant="outline" disabled={!address.trim() || loading || disabled}>
            {loading ? <SpinnerIcon className="animate-spin" aria-hidden /> : <MagnifyingGlassIcon aria-hidden />}
            불러오기
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          하위 페이지를 고를 수 있습니다. 앱의 Notion 통합이 연결된 페이지만 읽힙니다.
        </p>
      </form>

      {pages && (
        <div className="grid gap-2">
          <ul className="max-h-48 divide-y overflow-y-auto rounded-lg border" aria-label="Notion 페이지">
            {pages.map((p) => {
              const id = `${inputId}-${p.page_id}`;
              return (
                <li key={p.page_id} className="flex items-center gap-2.5 px-3 py-2">
                  <Checkbox
                    id={id}
                    checked={selected.has(p.page_id)}
                    onCheckedChange={(v) => toggle(p.page_id, v === true)}
                  />
                  <Label htmlFor={id} className="font-normal [overflow-wrap:anywhere]">
                    {p.title || "(제목 없음)"}
                  </Label>
                </li>
              );
            })}
          </ul>
          <Button
            variant="secondary"
            onClick={importSelected}
            disabled={selected.size === 0 || importing || disabled}
            className="justify-self-end"
          >
            {importing ? <SpinnerIcon className="animate-spin" aria-hidden /> : <DownloadSimpleIcon aria-hidden />}
            {selected.size}개 가져오기
          </Button>
        </div>
      )}

      {(error || failed.length > 0) && (
        <Alert variant="destructive">
          <WarningCircleIcon aria-hidden />
          <AlertTitle>{error ? "Notion에서 읽지 못했습니다" : `가져오지 못한 페이지 ${failed.length}개`}</AlertTitle>
          <AlertDescription>
            {error ?? (
              <ul className="list-disc pl-4">
                {failed.map((f) => (
                  <li key={f.page_id}>{f.error}</li>
                ))}
              </ul>
            )}
          </AlertDescription>
        </Alert>
      )}
    </div>
  );
}
