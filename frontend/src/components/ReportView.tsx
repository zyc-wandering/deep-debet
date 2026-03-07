import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  reportPath: string;
  markdown: string;
}

export function ReportView({ reportPath, markdown }: Props) {
  return (
    <section className="panel report-panel">
      <div className="section-head">
        <div>
          <p className="eyebrow">Report</p>
          <h2>主持人总结与最终报告</h2>
        </div>
        {reportPath && <span className="muted report-path">已写入本地</span>}
      </div>

      {reportPath && <p className="report-location">{reportPath}</p>}
      {!markdown && <p className="muted empty-block">辩论结束后，主持人会在这里输出总结、结论和报告全文。</p>}
      {markdown && (
        <article className="markdown-body">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
        </article>
      )}
    </section>
  );
}
