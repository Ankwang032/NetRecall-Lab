import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type Props = { label: string; count: number; pressed: boolean; onClick: () => void };

// 목록을 거르는 버튼 (주제·카테고리). 눌린 상태를 aria-pressed로 알린다
export function FilterButton({ label, count, pressed, onClick }: Props) {
  return (
    <Button variant={pressed ? "default" : "outline"} size="sm" aria-pressed={pressed} onClick={onClick}>
      {label}
      <span className={cn("tabular-nums", pressed ? "opacity-80" : "text-muted-foreground")}>{count}</span>
    </Button>
  );
}
