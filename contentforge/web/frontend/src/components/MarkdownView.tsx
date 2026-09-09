import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  children: string;
  highlightGaps?: boolean;
}

/** 在文本节点中把 [数据缺口：xxx] 替换为带样式的 span */
function renderChildren(text: string, highlight: boolean): React.ReactNode {
  if (!highlight) return text;
  const parts = text.split(/(\[数据缺口[：:][^\]]*\])/g);
  return parts.map((part, i) =>
    /^\[数据缺口[：:][^\]]*\]$/.test(part) ? (
      <span key={i} className="gap-highlight">{part}</span>
    ) : (
      part
    )
  );
}

export default function MarkdownView({ children, highlightGaps = false }: Props) {
  return (
    <div className="md-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={
          highlightGaps
            ? {
                p: ({ children, ...props }) => (
                  <p {...props}>{renderChildren(String(children), true)}</p>
                ),
                li: ({ children, ...props }) => (
                  <li {...props}>{renderChildren(String(children), true)}</li>
                ),
                td: ({ children, ...props }) => (
                  <td {...props}>{renderChildren(String(children), true)}</td>
                ),
              }
            : undefined
        }
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
