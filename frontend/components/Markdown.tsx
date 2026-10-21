import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

/** An answer as Markdown with maths ($…$ inline, $$…$$ blocks), so JEE/NEET formulas
 * read properly. Loaded with next/dynamic: only the doubt page downloads it.
 * Raw HTML in the text is not rendered (react-markdown's default), so an answer
 * can't inject markup. */
export default function Markdown({ children }: { children: string }) {
  return (
    <div className="answer-md">
      <ReactMarkdown remarkPlugins={[remarkMath]} rehypePlugins={[rehypeKatex]}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
