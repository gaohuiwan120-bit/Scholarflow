/** Lightweight Markdown renderer — no extra dependencies. */

import type { ReactNode } from "react";

function renderInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  // Non-greedy bold/italic; links; bare URLs.
  const re =
    /(\*\*[^*]+?\*\*|__[^_]+?__|`[^`]+?`|\[[^\]]+?\]\([^)]+?\)|https?:\/\/[^\s)<]+)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let key = 0;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const tok = m[0];
    if (
      (tok.startsWith("**") && tok.endsWith("**")) ||
      (tok.startsWith("__") && tok.endsWith("__"))
    ) {
      nodes.push(<strong key={key++}>{tok.slice(2, -2)}</strong>);
    } else if (tok.startsWith("`") && tok.endsWith("`")) {
      nodes.push(
        <code key={key++} className="md-inline-code">
          {tok.slice(1, -1)}
        </code>,
      );
    } else if (tok.startsWith("[")) {
      const mm = tok.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
      if (mm) {
        nodes.push(
          <a key={key++} href={mm[2]} target="_blank" rel="noreferrer">
            {mm[1]}
          </a>,
        );
      } else nodes.push(tok);
    } else {
      const href = tok.replace(/[.,;:]+$/, "");
      nodes.push(
        <a key={key++} href={href} target="_blank" rel="noreferrer">
          {href}
        </a>,
      );
    }
    last = m.index + tok.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

function isTableSep(line: string): boolean {
  const t = line.trim();
  return /^\|?[\s:|-]+\|[\s:|-]*\|?$/.test(t) && t.includes("-");
}

function isTableRow(line: string): boolean {
  const t = line.trim();
  return t.includes("|") && !isTableSep(t) && t.length > 2;
}

function splitCells(line: string): string[] {
  let t = line.trim();
  if (t.startsWith("|")) t = t.slice(1);
  if (t.endsWith("|")) t = t.slice(0, -1);
  return t.split("|").map((c) => c.trim());
}

function renderTable(rows: string[], key: string): ReactNode {
  if (!rows.length) return null;
  const header = splitCells(rows[0]);
  const bodyLines = rows.slice(1).filter((r) => !isTableSep(r));
  return (
    <div key={key} className="md-table-wrap">
      <table className="md-table">
        <thead>
          <tr>
            {header.map((c, i) => (
              <th key={i}>{renderInline(c)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {bodyLines.map((row, ri) => (
            <tr key={ri}>
              {splitCells(row).map((c, ci) => (
                <td key={ci}>{renderInline(c)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function Markdown({ text }: { text: string }) {
  if (!text) return null;
  const blocks = text.split(/```/);
  const out: ReactNode[] = [];

  for (let i = 0; i < blocks.length; i++) {
    const chunk = blocks[i];
    if (i % 2 === 1) {
      const nl = chunk.indexOf("\n");
      const code = nl >= 0 ? chunk.slice(nl + 1) : chunk;
      const lang = nl >= 0 ? chunk.slice(0, nl).trim() : "";
      out.push(
        <pre key={`c-${i}`} className="md-code">
          {lang ? <span className="md-lang">{lang}</span> : null}
          <code>{code.replace(/\n$/, "")}</code>
        </pre>,
      );
      continue;
    }

    const lines = chunk.split("\n");
    let para: string[] = [];
    let listBuf: { ordered: boolean; items: string[] } | null = null;
    let tableBuf: string[] = [];

    const flushPara = (keyBase: string) => {
      if (!para.length) return;
      out.push(
        <p key={keyBase} className="md-p">
          {renderInline(para.join("\n"))}
        </p>,
      );
      para = [];
    };

    const flushList = (keyBase: string) => {
      if (!listBuf?.items.length) {
        listBuf = null;
        return;
      }
      const Tag = listBuf.ordered ? "ol" : "ul";
      out.push(
        <Tag key={keyBase} className="md-list">
          {listBuf.items.map((item, idx) => (
            <li key={idx} className="md-li">
              {renderInline(item)}
            </li>
          ))}
        </Tag>,
      );
      listBuf = null;
    };

    const flushTable = (keyBase: string) => {
      if (!tableBuf.length) return;
      out.push(renderTable(tableBuf, keyBase));
      tableBuf = [];
    };

    lines.forEach((line, li) => {
      const t = line.trimEnd();
      const trimmed = t.trim();

      if (isTableRow(trimmed) || (tableBuf.length > 0 && isTableSep(trimmed))) {
        flushPara(`p-${i}-${li}-pre`);
        flushList(`l-${i}-${li}-pre`);
        tableBuf.push(trimmed);
        return;
      }
      if (tableBuf.length) flushTable(`tbl-${i}-${li}`);

      if (/^#{1,3}\s+/.test(trimmed)) {
        flushPara(`p-${i}-${li}-pre`);
        flushList(`l-${i}-${li}-pre`);
        const level = trimmed.match(/^#+/)?.[0].length ?? 1;
        const content = trimmed.replace(/^#{1,3}\s+/, "");
        const Tag = (level === 1 ? "h3" : level === 2 ? "h4" : "h5") as
          | "h3"
          | "h4"
          | "h5";
        out.push(
          <Tag key={`h-${i}-${li}`} className="md-h">
            {renderInline(content)}
          </Tag>,
        );
        return;
      }

      const ul = trimmed.match(/^[-*]\s+(.*)$/);
      const ol = trimmed.match(/^\d+\.\s+(.*)$/);
      if (ul || ol) {
        flushPara(`p-${i}-${li}-pre`);
        const ordered = Boolean(ol);
        const body = (ul ? ul[1] : ol![1]) ?? "";
        if (!listBuf || listBuf.ordered !== ordered) {
          flushList(`l-${i}-${li}-switch`);
          listBuf = { ordered, items: [body] };
        } else {
          listBuf.items.push(body);
        }
        return;
      }

      if (!trimmed) {
        flushPara(`p-${i}-${li}`);
        flushList(`l-${i}-${li}`);
        return;
      }

      flushList(`l-${i}-${li}-pre`);
      para.push(t);
    });

    flushTable(`tbl-${i}-end`);
    flushList(`l-${i}-end`);
    flushPara(`p-${i}-end`);
  }

  return <div className="md-body">{out}</div>;
}
