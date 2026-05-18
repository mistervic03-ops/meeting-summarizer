export type ExportFormat = "docx" | "markdown" | "pdf" | "text";

interface MeetingExportOptions {
  filename: string;
  format: ExportFormat;
  markdown: string;
  title: string;
}

const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
const UTF8_FLAG = 0x0800;

/**
 * 회의록을 선택한 형식으로 내보냅니다.
 */
export function exportMeetingDocument({ filename, format, markdown, title }: MeetingExportOptions) {
  if (format === "pdf") {
    printMarkdownDocument(title, markdown);
    return;
  }

  if (format === "docx") {
    downloadBlob(createDocxBlob(title, markdown), `${filename}.docx`);
    return;
  }

  const content = format === "text" ? markdownToPlainText(markdown) : markdown;
  const extension = format === "text" ? "txt" : "md";
  const mime = format === "text" ? "text/plain;charset=utf-8" : "text/markdown;charset=utf-8";

  downloadBlob(new Blob([content], { type: mime }), `${filename}.${extension}`);
}

/**
 * 파일명에 부적합한 문자를 제거합니다.
 */
export function sanitizeExportFilename(title: string): string {
  return (
    title
      .replace(/\.[^.]+$/, "")
      .replace(/[\\/:*?"<>|]/g, " ")
      .replace(/\s+/g, " ")
      .trim() || "meeting_minutes"
  );
}

/**
 * Blob을 브라우저 다운로드로 저장합니다.
 */
function downloadBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");

  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * 브라우저 인쇄 흐름을 사용해 PDF 저장을 유도합니다.
 */
function printMarkdownDocument(title: string, markdown: string) {
  const frame = document.createElement("iframe");

  frame.style.position = "fixed";
  frame.style.right = "0";
  frame.style.bottom = "0";
  frame.style.width = "0";
  frame.style.height = "0";
  frame.style.border = "0";
  frame.title = "회의록 PDF 내보내기";
  document.body.appendChild(frame);

  const frameDocument = frame.contentDocument;
  if (!frameDocument) {
    document.body.removeChild(frame);
    return;
  }

  frameDocument.open();
  frameDocument.write(renderPrintHtml(title, markdown));
  frameDocument.close();

  window.setTimeout(() => {
    frame.contentWindow?.focus();
    frame.contentWindow?.print();
    window.setTimeout(() => document.body.removeChild(frame), 1000);
  }, 50);
}

/**
 * 인쇄용 HTML 문서를 만듭니다.
 */
function renderPrintHtml(title: string, markdown: string): string {
  return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    @page { margin: 22mm 20mm; }
    body {
      color: #172033;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
      font-size: 11pt;
      line-height: 1.72;
    }
    h1 { font-size: 19pt; line-height: 1.25; margin: 0 0 18pt; }
    h2 { border-top: 1px solid #d8dee8; font-size: 14pt; margin: 22pt 0 8pt; padding-top: 14pt; }
    h3 { font-size: 12pt; margin: 16pt 0 6pt; }
    p { margin: 0 0 10pt; }
    ul, ol { margin: 0 0 12pt 18pt; padding: 0; }
    li { margin: 0 0 4pt; }
  </style>
</head>
<body>
  ${markdownToHtml(markdown)}
</body>
</html>`;
}

/**
 * 간단한 Markdown을 인쇄 가능한 HTML로 변환합니다.
 */
function markdownToHtml(markdown: string): string {
  const html: string[] = [];
  let isListOpen = false;

  markdown.split("\n").forEach((line) => {
    const trimmed = line.trim();
    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    const bullet = /^[-*]\s+(.+)$/.exec(trimmed);

    if (!trimmed) {
      if (isListOpen) {
        html.push("</ul>");
        isListOpen = false;
      }
      return;
    }

    if (heading) {
      if (isListOpen) {
        html.push("</ul>");
        isListOpen = false;
      }
      html.push(`<h${heading[1].length}>${renderInlineMarkdown(heading[2])}</h${heading[1].length}>`);
      return;
    }

    if (bullet) {
      if (!isListOpen) {
        html.push("<ul>");
        isListOpen = true;
      }
      html.push(`<li>${renderInlineMarkdown(bullet[1])}</li>`);
      return;
    }

    if (isListOpen) {
      html.push("</ul>");
      isListOpen = false;
    }
    html.push(`<p>${renderInlineMarkdown(trimmed)}</p>`);
  });

  if (isListOpen) {
    html.push("</ul>");
  }

  return html.join("\n");
}

/**
 * DOCX Blob을 생성합니다.
 */
function createDocxBlob(title: string, markdown: string): Blob {
  const documentXml = renderDocumentXml(title, markdown);
  const files = [
    {
      name: "[Content_Types].xml",
      content:
        '<?xml version="1.0" encoding="UTF-8"?>' +
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>' +
        '<Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>' +
        "</Types>"
    },
    {
      name: "_rels/.rels",
      content:
        '<?xml version="1.0" encoding="UTF-8"?>' +
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' +
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>' +
        "</Relationships>"
    },
    {
      name: "word/document.xml",
      content: documentXml
    }
  ];

  return new Blob([createZip(files)], { type: DOCX_MIME });
}

/**
 * Word 문서 본문 XML을 만듭니다.
 */
function renderDocumentXml(title: string, markdown: string): string {
  const body = [
    renderDocxParagraph(title, "title"),
    ...markdown
      .split("\n")
      .map((line) => renderMarkdownLineAsDocxParagraph(line))
      .filter(Boolean)
  ].join("");

  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    ${body}
    <w:sectPr>
      <w:pgSz w:w="11906" w:h="16838"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/>
    </w:sectPr>
  </w:body>
</w:document>`;
}

/**
 * Markdown 한 줄을 Word 문단으로 변환합니다.
 */
function renderMarkdownLineAsDocxParagraph(line: string): string {
  const trimmed = line.trim();
  const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
  const bullet = /^[-*]\s+(.+)$/.exec(trimmed);

  if (!trimmed) {
    return "";
  }

  if (heading) {
    return renderDocxParagraph(stripMarkdownInline(heading[2]), heading[1].length === 1 ? "heading1" : "heading2");
  }

  if (bullet) {
    return renderDocxParagraph(`• ${stripMarkdownInline(bullet[1])}`, "body");
  }

  return renderDocxParagraph(stripMarkdownInline(trimmed), "body");
}

/**
 * Word 문단 XML을 만듭니다.
 */
function renderDocxParagraph(text: string, variant: "body" | "heading1" | "heading2" | "title"): string {
  const settings = {
    body: { after: 180, before: 0, bold: false, size: 22 },
    heading1: { after: 160, before: 340, bold: true, size: 30 },
    heading2: { after: 120, before: 260, bold: true, size: 26 },
    title: { after: 360, before: 0, bold: true, size: 36 }
  }[variant];
  const bold = settings.bold ? "<w:b/>" : "";

  return `<w:p>
    <w:pPr><w:spacing w:before="${settings.before}" w:after="${settings.after}" w:line="360" w:lineRule="auto"/></w:pPr>
    <w:r><w:rPr>${bold}<w:sz w:val="${settings.size}"/></w:rPr><w:t xml:space="preserve">${escapeXml(text)}</w:t></w:r>
  </w:p>`;
}

/**
 * 간단한 Markdown을 일반 텍스트로 변환합니다.
 */
function markdownToPlainText(markdown: string): string {
  return markdown
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "- ")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .trim();
}

/**
 * 인라인 Markdown을 HTML로 렌더링합니다.
 */
function renderInlineMarkdown(text: string): string {
  return escapeHtml(text)
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/__(.*?)__/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "$1");
}

/**
 * 인라인 Markdown 기호를 제거합니다.
 */
function stripMarkdownInline(text: string): string {
  return text
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1");
}

/**
 * XML 특수 문자를 이스케이프합니다.
 */
function escapeXml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/**
 * HTML 특수 문자를 이스케이프합니다.
 */
function escapeHtml(text: string): string {
  return escapeXml(text).replace(/'/g, "&#39;");
}

/**
 * 외부 의존성 없이 저장 방식 ZIP을 생성합니다.
 */
function createZip(files: Array<{ content: string; name: string }>): ArrayBuffer {
  const encoder = new TextEncoder();
  const localParts: Uint8Array[] = [];
  const centralParts: Uint8Array[] = [];
  let offset = 0;

  files.forEach((file) => {
    const name = encoder.encode(file.name);
    const content = encoder.encode(file.content);
    const crc = crc32(content);
    const localHeader = createLocalFileHeader(name, content, crc);
    const centralHeader = createCentralDirectoryHeader(name, content, crc, offset);

    localParts.push(localHeader, content);
    centralParts.push(centralHeader);
    offset += localHeader.length + content.length;
  });

  const centralSize = centralParts.reduce((size, part) => size + part.length, 0);
  const endRecord = createEndOfCentralDirectory(files.length, centralSize, offset);

  return concatUint8Arrays([...localParts, ...centralParts, endRecord]).buffer as ArrayBuffer;
}

/**
 * ZIP 로컬 파일 헤더를 만듭니다.
 */
function createLocalFileHeader(name: Uint8Array, content: Uint8Array, crc: number): Uint8Array {
  const header = new Uint8Array(30 + name.length);
  const view = new DataView(header.buffer);

  view.setUint32(0, 0x04034b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, UTF8_FLAG, true);
  view.setUint16(8, 0, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint32(14, crc, true);
  view.setUint32(18, content.length, true);
  view.setUint32(22, content.length, true);
  view.setUint16(26, name.length, true);
  view.setUint16(28, 0, true);
  header.set(name, 30);

  return header;
}

/**
 * ZIP 중앙 디렉터리 헤더를 만듭니다.
 */
function createCentralDirectoryHeader(name: Uint8Array, content: Uint8Array, crc: number, offset: number): Uint8Array {
  const header = new Uint8Array(46 + name.length);
  const view = new DataView(header.buffer);

  view.setUint32(0, 0x02014b50, true);
  view.setUint16(4, 20, true);
  view.setUint16(6, 20, true);
  view.setUint16(8, UTF8_FLAG, true);
  view.setUint16(10, 0, true);
  view.setUint16(12, 0, true);
  view.setUint16(14, 0, true);
  view.setUint32(16, crc, true);
  view.setUint32(20, content.length, true);
  view.setUint32(24, content.length, true);
  view.setUint16(28, name.length, true);
  view.setUint16(30, 0, true);
  view.setUint16(32, 0, true);
  view.setUint16(34, 0, true);
  view.setUint16(36, 0, true);
  view.setUint32(38, 0, true);
  view.setUint32(42, offset, true);
  header.set(name, 46);

  return header;
}

/**
 * ZIP 종료 레코드를 만듭니다.
 */
function createEndOfCentralDirectory(fileCount: number, centralSize: number, centralOffset: number): Uint8Array {
  const record = new Uint8Array(22);
  const view = new DataView(record.buffer);

  view.setUint32(0, 0x06054b50, true);
  view.setUint16(4, 0, true);
  view.setUint16(6, 0, true);
  view.setUint16(8, fileCount, true);
  view.setUint16(10, fileCount, true);
  view.setUint32(12, centralSize, true);
  view.setUint32(16, centralOffset, true);
  view.setUint16(20, 0, true);

  return record;
}

/**
 * Uint8Array 조각들을 하나로 합칩니다.
 */
function concatUint8Arrays(parts: Uint8Array[]): Uint8Array {
  const length = parts.reduce((size, part) => size + part.length, 0);
  const combined = new Uint8Array(length);
  let offset = 0;

  parts.forEach((part) => {
    combined.set(part, offset);
    offset += part.length;
  });

  return combined;
}

/**
 * ZIP에 필요한 CRC32 값을 계산합니다.
 */
function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff;

  bytes.forEach((byte) => {
    crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  });

  return (crc ^ 0xffffffff) >>> 0;
}

const CRC_TABLE = Array.from({ length: 256 }, (_, index) => {
  let value = index;

  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1;
  }

  return value >>> 0;
});
