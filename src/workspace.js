// Each document owns its editor state and its undo/redo branches.
export const DEFAULT_ADJUST = { x: 0, y: 0, width: 1, height: 1, angle: 0, blur: 0, darkness: 1 };
export const HISTORY_LIMIT = 5;
export const EMPTY_EDITOR = {
  doc: null, selection: null, tool: 'rectangle', zoom: null, fitZoom: 1,
  originalText: '', originalManuallyEdited: false, replacement: '', font: 'auto', contrast: 'auto',
  ocr: null, ocrRetry: 0, adjust: DEFAULT_ADJUST, candidate: null,
  history: [], future: [], showOriginal: false, showSelection: true, showAdjust: false,
  scroll: { left: 0, top: 0 },
};
export const EMPTY_WORKSPACE = { tabs: [], activeId: null };

export function createDocument({ id, src, name, width, height, preset }) {
  return {
    ...EMPTY_EDITOR, id,
    doc: { base: src, original: src, name, width, height },
    selection: preset?.selection || null,
    originalText: preset?.original || '', replacement: preset?.replacement || '',
  };
}

function undo(tab) {
  if (tab.candidate) {
    const preview = { kind: 'preview', candidate: tab.candidate, selection: tab.selection,
      originalText: tab.originalText, originalManuallyEdited:tab.originalManuallyEdited, replacement: tab.replacement, font: tab.font,
      contrast: tab.contrast, adjust: tab.adjust, ocr: tab.ocr, ocrRetry: tab.ocrRetry };
    return { ...tab, candidate: null, showOriginal: false, future: [...tab.future, preview] };
  }
  if (!tab.history.length) return tab;
  return { ...tab, doc: { ...tab.doc, base: tab.history.at(-1) },
    history: tab.history.slice(0,-1), future: [...tab.future, { kind:'image', image:tab.doc.base }],
    selection:null, ocr:null, showOriginal:false };
}

function redo(tab) {
  const next = tab.future.at(-1);
  if (!next) return tab;
  const future = tab.future.slice(0,-1);
  if (next.kind === 'preview') {
    const { kind, ...preview } = next;
    return { ...tab, ...preview, future, showOriginal:false };
  }
  return { ...tab, doc:{ ...tab.doc, base:next.image },
    history:[...tab.history, tab.doc.base].slice(-HISTORY_LIMIT), future,
    candidate:null, selection:null, ocr:null, showOriginal:false };
}

export function workspaceReducer(state, action) {
  if (action.type === 'open') {
    if (!action.documents.length) return state;
    return { tabs:[...state.tabs,...action.documents], activeId:action.documents.at(-1).id };
  }
  if (action.type === 'activate') {
    return state.tabs.some(t => t.id === action.id) ? { ...state, activeId:action.id } : state;
  }
  if (action.type === 'close') {
    const index = state.tabs.findIndex(t => t.id === action.id);
    if (index < 0) return state;
    const tabs = state.tabs.filter(t => t.id !== action.id);
    const activeId = state.activeId === action.id ? (tabs[Math.min(index,tabs.length-1)]?.id || null) : state.activeId;
    return { tabs, activeId };
  }
  return { ...state, tabs:state.tabs.map(tab => {
    if (tab.id !== action.id) return tab;
    switch (action.type) {
      case 'set': return { ...tab, [action.key]:typeof action.value === 'function' ? action.value(tab[action.key]) : action.value };
      case 'invalidate': return { ...tab, candidate:null, future:[] };
      case 'cancelSelection': return { ...tab, selection:null, candidate:null, ocr:null, showOriginal:false,
        future:tab.future.filter(step => step.kind !== 'preview') };
      case 'adopt':
        if (!tab.candidate) return tab;
        return { ...tab, doc:{ ...tab.doc, base:tab.candidate.image },
          history:[...tab.history,tab.doc.base].slice(-HISTORY_LIMIT), future:[], candidate:null,
          selection:null, ocr:null, showOriginal:false, adjust:DEFAULT_ADJUST, font:'auto' };
      case 'undo': return undo(tab);
      case 'redo': return redo(tab);
      default: return tab;
    }
  }) };
}
