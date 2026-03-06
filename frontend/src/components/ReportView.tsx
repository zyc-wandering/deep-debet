import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  reportPath: string;
  markdown: string;
}

export function ReportView({ reportPath, markdown }: Props) {
  return (
    <section className="panel report-panel">
      <h2>主持人总结与报告</h2>
      {reportPath && <p className="muted">已保存到本地：{reportPath}</p>}
      {!markdown && <p className="muted">辩论结束后会在这里展示报告。</p>}
      {markdown && (
        <article className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </article>
      )}
    </section>
  );
}

