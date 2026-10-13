export interface EditorSelection {
  start: number;
  end: number;
}

interface EditorInsertionOptions {
  before: string;
  after?: string;
  defaultText?: string;
  replaceSelection?: boolean;
}

export const insertEditorText = (
  content: string,
  selection: EditorSelection,
  { before, after = '', defaultText = '', replaceSelection = false }: EditorInsertionOptions,
) => {
  const start = Math.max(0, Math.min(selection.start, content.length));
  const end = Math.max(start, Math.min(selection.end, content.length));
  const selected = replaceSelection ? '' : (content.substring(start, end) || defaultText);
  const selectionStart = start + before.length;
  return {
    content: content.substring(0, start) + before + selected + after + content.substring(end),
    selection: { start: selectionStart, end: selectionStart + selected.length },
  };
};
