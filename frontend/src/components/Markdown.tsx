import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// 개념 본문. GFM(표·취소선·체크리스트)만 켠다. 본문의 HTML은 그리지 않는다(react-markdown 기본)
// react-markdown이 넘기는 node는 DOM 속성이 아니라서 빼고 넘긴다
const components: Components = {
  h1: ({ node: _, ...p }) => <h2 className="mt-8 mb-3 text-xl font-semibold tracking-tight first:mt-0" {...p} />,
  h2: ({ node: _, ...p }) => <h2 className="mt-8 mb-3 border-b pb-1.5 text-lg font-semibold tracking-tight first:mt-0" {...p} />,
  h3: ({ node: _, ...p }) => <h3 className="mt-6 mb-2 font-semibold" {...p} />,
  h4: ({ node: _, ...p }) => <h4 className="mt-5 mb-2 font-medium" {...p} />,
  p: ({ node: _, ...p }) => <p className="my-3 leading-relaxed" {...p} />,
  ul: ({ node: _, ...p }) => <ul className="my-3 list-disc space-y-1 pl-6 marker:text-muted-foreground" {...p} />,
  ol: ({ node: _, ...p }) => <ol className="my-3 list-decimal space-y-1 pl-6 marker:text-muted-foreground" {...p} />,
  li: ({ node: _, ...p }) => <li className="leading-relaxed" {...p} />,
  blockquote: ({ node: _, ...p }) => <blockquote className="my-4 rounded-r-md border-l-4 border-primary/40 bg-accent/40 px-4 py-1" {...p} />,
  hr: () => <hr className="my-6" />,
  a: ({ node: _, href, ...p }) => <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2" {...p} />,
  code: ({ node: _, ...p }) => <code className="rounded bg-muted px-1 py-0.5 font-mono text-[0.85em]" {...p} />,
  pre: ({ node: _, ...p }) => (
    <pre className="my-4 overflow-x-auto rounded-md bg-muted p-3 font-mono text-[0.82rem] leading-relaxed [&_code]:bg-transparent [&_code]:p-0 [&_code]:text-[length:inherit]" {...p} />
  ),
  table: ({ node: _, ...p }) => (
    <div className="my-4 overflow-x-auto rounded-md border">
      <table className="w-full border-collapse text-sm" {...p} />
    </div>
  ),
  th: ({ node: _, ...p }) => <th className="border-b bg-muted/60 px-3 py-2 text-left font-medium" {...p} />,
  td: ({ node: _, ...p }) => <td className="border-b px-3 py-2 align-top" {...p} />,
};

export function Markdown({ text }: { text: string }) {
  return (
    <div className="text-[0.95rem]">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>
    </div>
  );
}
