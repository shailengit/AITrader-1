import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

export function ReportView({ markdown }: { markdown: string }) {
  return (
    <div className="prose prose-invert max-w-none prose-headings:text-zinc-100 prose-p:text-zinc-300 prose-strong:text-zinc-100 prose-li:text-zinc-300">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
    </div>
  );
}
