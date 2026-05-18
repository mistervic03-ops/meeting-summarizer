const EMOJI_PATTERN = /[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}\u{FE0F}]/gu;

const SECTION_LABEL_REPLACEMENTS: Array<[RegExp, string]> = [
  [/빠른\s*요약/g, "요약"],
  [/전체\s*회의록/g, "회의록"],
  [/확인\s*필요/g, "검토 필요"]
];

/**
 * Removes decorative markers from short UI strings without rewriting their content.
 */
export function normalizeDisplayText(text: string): string {
  return applySectionLabelReplacements(text.replace(EMOJI_PATTERN, ""))
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/^\s*#{1,6}\s+/, "")
    .replace(/^\s*[-*•]\s+/, "")
    .replace(/\s{2,}/g, " ")
    .trim();
}

/**
 * Cleans generated Markdown for article-style rendering while preserving model content.
 */
export function normalizeMarkdownForDisplay(markdown: string): string {
  return applySectionLabelReplacements(markdown.replace(EMOJI_PATTERN, ""))
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+$/gm, "")
    .replace(/\n{3,}/g, "\n\n")
    .replace(/^(#{1,6})\s+\1\s+/gm, "$1 ")
    .trim();
}

/**
 * Maps verbose generated section labels to the calmer labels used in the app.
 */
function applySectionLabelReplacements(text: string): string {
  return SECTION_LABEL_REPLACEMENTS.reduce((currentText, [pattern, replacement]) => currentText.replace(pattern, replacement), text);
}
