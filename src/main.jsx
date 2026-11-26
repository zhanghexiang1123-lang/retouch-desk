import React, { useEffect, useLayoutEffect, useReducer, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowDownToLine, ArrowLeftRight, Check, ChevronDown, CircleHelp, Cpu, Crosshair, FileImage, FolderOpen, Hand, LoaderCircle, Maximize2, Move, PenTool, Plus, RotateCcw, ScanLine, ShieldCheck, SquareDashedMousePointer, Undo2, Redo2, Upload, X, ZoomIn, ZoomOut } from 'lucide-react';
import './styles.css';
import { DEFAULT_ADJUST, EMPTY_EDITOR, EMPTY_WORKSPACE, createDocument, workspaceReducer } from './workspace.js';

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const clamp = (n, min, max) => Math.min(max, Math.max(min, n));

function App() {
  const [session, setSession] = useState(null);
  const [connection, setConnection] = useState('connecting');
  const [workspace, dispatch] = useReducer(workspaceReducer, EMPTY_WORKSPACE);
  const active = workspace.tabs.find(tab => tab.id === workspace.activeId) || EMPTY_EDITOR;
  const activeId = workspace.activeId;
  const { doc, selection, tool, zoom: savedZoom, fitZoom, originalText, replacement, font, contrast,
    ocr, ocrRetry, adjust, candidate, history, future, showOriginal, showSelection, showAdjust } = active;
  const zoom = savedZoom ?? fitZoom;
  const field = key => value => dispatch({ type:'set', id:activeId, key, value });
  const setDoc=field('doc'), setSelection=field('selection'), setTool=field('tool');
  const setZoom=value=>dispatch({type:'set',id:activeId,key:'zoom',value:typeof value==='function' ? previous=>value(previous ?? fitZoom) : value});
  const setFitZoom=field('fitZoom'), setOriginalText=field('originalText'), setReplacement=field('replacement');
  const setFont=field('font'), setContrast=field('contrast'), setOcr=field('ocr'), setOcrRetry=field('ocrRetry');
  const setAdjust=field('adjust'), setCandidate=field('candidate'), setShowOriginal=field('showOriginal');
  const setShowSelection=field('showSelection'), setShowAdjust=field('showAdjust');
  const [draft, setDraft] = useState(null);
  const [opening, setOpening] = useState(false);
  const [job, setJob] = useState(null);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [help, setHelp] = useState(false);
  const inputRef = useRef(null);
  const openingRef = useRef(false);
  const tabListRef = useRef(null);
  const surfaceRef = useRef(null);
  const viewportRef = useRef(null);
  const dragRef = useRef(null);
  const epoch = useRef(0);
  const jobRef = useRef(null);
  const pollController = useRef(null);
  const ocrController = useRef(null);
  const ocrRevision = useRef(0);
  const manualTextRevision = useRef(0);
  const busy = Boolean(job);

  useEffect(() => {
    const abort = new AbortController();
    fetch('/api/session', { signal: abort.signal }).then(r => r.json()).then(data => {
      if (!data.token) throw Error('服务不可用');
      setSession(data); setConnection('ready');
    }).catch(e => { if (e.name !== 'AbortError') setConnection('error'); });
    return () => { abort.abort(); epoch.current++; pollController.current?.abort(); ocrController.current?.abort(); };
  }, []);
  useEffect(() => {
    if (!message) return;
    const timer = setTimeout(() => setMessage(''), 4200);
    return () => clearTimeout(timer);
  }, [message]);
  useEffect(() => {
    const element = viewportRef.current;
    if (!element || !doc) return;
    const update = () => {
      const ratio = Math.min((element.clientWidth - 80) / doc.width, (element.clientHeight - 64) / doc.height, 2);
      setFitZoom(Math.max(.15, ratio));
    };
    const observer = new ResizeObserver(update);
    observer.observe(element); update();
    return () => observer.disconnect();
  }, [activeId, doc?.width, doc?.height]);
  useLayoutEffect(() => {
    const viewport = viewportRef.current;
    if (viewport) { viewport.scrollLeft=active.scroll.left; viewport.scrollTop=active.scroll.top; }
    tabListRef.current?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block:'nearest', inline:'nearest' });
  }, [activeId]);


  async function api(path, data, signal) {
    const response = await fetch(path, { method: data === undefined ? 'GET' : 'POST', headers: { 'X-Retouch-Token': session?.token || '', ...(data === undefined ? {} : { 'Content-Type': 'application/json' }) }, ...(data === undefined ? {} : { body: JSON.stringify(data) }), signal });
    let result;
    try { result = await response.json(); } catch { throw Error('无法连接处理服务，请重新打开应用。'); }
    if (!response.ok) throw Error(result.error || '请求失败，请重试。');
    return result;
  }
  useEffect(() => {
    const revision = ++ocrRevision.current;
    if (!selection || !doc || !session) { setOcr(null); return; }
    // Reuse completed recognition when returning to a tab; preserve manual corrections and previews.
    if (ocr && ocr.status !== 'running' && ocr.image === doc.base && ocr.selection === selection
        && ocr.contrast === contrast && ocr.retry === ocrRetry) return;
    const controller = new AbortController();
    ocrController.current = controller;
    const textRevision = manualTextRevision.current;
    setOcr({ status: 'running' });
    // Debounce selection changes, without preventing text entry while OCR runs.
    const timer = setTimeout(async () => {
      try {
        const result = await api('/api/ocr', { image: doc.base, selection, contrast }, controller.signal);
        if (controller.signal.aborted || revision !== ocrRevision.current) return;
        const applied = Boolean(result.text) && result.text.length <= 40 && !active.originalManuallyEdited && textRevision === manualTextRevision.current;
        if (applied) { setOriginalText(result.text); setCandidate(null); }
        setOcr({ ...result, status: result.text ? 'done' : 'empty', applied, image:doc.base, selection, contrast, retry:ocrRetry });
      } catch (e) {
        if (!controller.signal.aborted && revision === ocrRevision.current)
          setOcr({ status:'error', message:e.message, image:doc.base, selection, contrast, retry:ocrRetry });
      }
    }, 150);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [activeId, selection, doc?.base, session?.token, contrast, ocrRetry]);

  function invalidate() { dispatch({type:'invalidate',id:activeId}); setError(''); }
  function changeSetting(setter, value) { setter(value); invalidate(); }
  function saveViewport() {
    if (activeId && viewportRef.current) dispatch({type:'set',id:activeId,key:'scroll',value:{left:viewportRef.current.scrollLeft,top:viewportRef.current.scrollTop}});
  }
  function interruptOcr() { ocrController.current?.abort(); ocrRevision.current++; manualTextRevision.current++; }
  function activateTab(id) {
    if (id === activeId) return;
    saveViewport(); interruptOcr(); dragRef.current=null; setDraft(null); setError('');
    dispatch({type:'activate',id});
  }
  function closeTab(id) {
    if (job?.tabId === id) cancelJob();
    if (id === activeId) { interruptOcr(); dragRef.current=null; setDraft(null); setError(''); }
    dispatch({type:'close',id});
  }
  function cancelSelection() {
    if (!selection && !draft) return;
    if (job?.tabId === activeId) cancelJob();
    interruptOcr(); dragRef.current=null; setDraft(null);
    dispatch({type:'cancelSelection',id:activeId}); setError('');
    setMessage('已取消框选，当前底图保持不变。');
  }
  useEffect(() => {
    function handleKey(event) {
      const typing = event.target.closest?.('input, textarea, select, [contenteditable="true"]');
      if (event.key === 'Escape' && !help) { event.preventDefault(); cancelSelection(); }
      if (!typing && !busy && (event.ctrlKey || event.metaKey)) {
        const key = event.key.toLowerCase();
        if (key === 'z') { event.preventDefault(); event.shiftKey ? redo() : undo(); }
        else if (key === 'y') { event.preventDefault(); redo(); }
      }
    }
    window.addEventListener('keydown',handleKey);
    return () => window.removeEventListener('keydown',handleKey);
  });
  async function decodeDocument(src, name, preset) {
    const image = new Image(); image.src = src;
    try { await image.decode(); } catch { throw Error(`${name}：图片无法读取，请选择 PNG、JPEG 或 WebP。`); }
    if (image.naturalWidth*image.naturalHeight > 24000000) throw Error(`${name}：图片超过 2400 万像素，请先缩小。`);
    return createDocument({id:crypto.randomUUID(),src,name,width:image.naturalWidth,height:image.naturalHeight,preset});
  }
  function addDocuments(documents) {
    saveViewport(); interruptOcr(); setDraft(null); dragRef.current=null; setError('');
    dispatch({type:'open',documents});
  }
  async function upload(files) {
    if (busy || openingRef.current) return;
    const list=Array.from(files || []);
    if (!list.length) return;
    openingRef.current=true; setOpening(true); setError('');
    const documents=[], failures=[];
    try {
      for (const file of list) {
        try {
          if (!/^image\/(png|jpeg|webp)$/.test(file.type)) throw Error(`${file.name}：支持 PNG、JPEG 和 WebP 图片。`);
          if (file.size > 28000000) throw Error(`${file.name}：文件超过 28MB，请先缩小。`);
          const src=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('文件读取失败'));reader.readAsDataURL(file);});
          documents.push(await decodeDocument(src,file.name));
        } catch (e) { failures.push(e.message || '无法打开图片。'); }
      }
      if (documents.length) { addDocuments(documents); setMessage(`已打开 ${documents.length} 张图片，可通过顶部标签切换。`); }
      if (failures.length) setError(failures.join('；'));
    } finally { openingRef.current=false; setOpening(false); }
  }
  async function openSample() {
    if (busy || openingRef.current) return;
    openingRef.current=true; setOpening(true);
    try { const result=await api('/api/sample'); addDocuments([await decodeDocument(result.image,result.name,result)]); setMessage('验收样图已在新标签打开。'); }
    catch (e) { setError(e.message); }
    finally { openingRef.current=false; setOpening(false); }
  }
  async function generate() {
    if (!selection || busy || !doc || !session) return;
    const revision = ++epoch.current;
    const targetId = activeId;
    dispatch({type:'set',id:targetId,key:'future',value:[]});
    const controller = new AbortController(); pollController.current = controller;
    setError(''); setCandidate(null); setShowOriginal(false); setJob({ message: '准备分析原字与背景', progress: .02, tabId:targetId });
    try {
      const task = await api('/api/edit', { image: doc.base, selection, original: originalText, replacement, font, contrast, adjustments: adjust }, controller.signal);
      jobRef.current = task.id;
      while (revision === epoch.current) {
        const status = await api('/api/jobs/' + task.id, undefined, controller.signal);
        if (revision !== epoch.current) return;
        if (status.status === 'done') { setCandidate(status.result); setMessage('预览已生成。请检查文字与放大对照后采用。'); break; }
        if (status.status === 'error' || status.status === 'cancelled') throw Error(status.message);
        setJob({...status,tabId:targetId}); await sleep(350);
      }
    } catch (e) { if (revision === epoch.current && e.name !== 'AbortError') setError(e.message); }
    finally { if (revision === epoch.current) { setJob(null); jobRef.current = null; } }
  }
  async function cancelJob() {
    epoch.current++; pollController.current?.abort();
    const id = jobRef.current; jobRef.current = null;
    setJob(null);
    if (id) { try { await api('/api/cancel', { id }); } catch (e) { setError(e.message); } }
    setMessage('本次处理已取消。');
  }
  function point(event) {
    const rect = surfaceRef.current.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width * doc.width, 0, doc.width), y: clamp((event.clientY - rect.top) / rect.height * doc.height, 0, doc.height) };
  }
  function pointerDown(event) {
    if (!doc || busy || opening || event.button !== 0) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    if (tool === 'pan') { dragRef.current = { pan: true, x: event.clientX, y: event.clientY, left: viewportRef.current.scrollLeft, top: viewportRef.current.scrollTop }; return; }
    const p = point(event); dragRef.current = { start: p, points: [p] };
    setDraft({ x: p.x, y: p.y, w: 0, h: 0, mode: tool, points: [p] }); invalidate();
  }
  function pointerMove(event) {
    const drag = dragRef.current;
    if (!drag) return;
    if (drag.pan) { viewportRef.current.scrollLeft = drag.left - event.clientX + drag.x; viewportRef.current.scrollTop = drag.top - event.clientY + drag.y; return; }
    const p = point(event);
    let points;
    if (tool === 'freehand') {
      const last = drag.points[drag.points.length - 1];
      if (Math.hypot(p.x - last.x, p.y - last.y) > .7 && drag.points.length < 5000) drag.points.push(p);
      points = drag.points.slice();
    } else points = [drag.start, p];
    const xs = points.map(p => p.x), ys = points.map(p => p.y);
    setDraft({ x: Math.min(...xs), y: Math.min(...ys), w: Math.max(...xs) - Math.min(...xs), h: Math.max(...ys) - Math.min(...ys), mode: tool, points: tool === 'freehand' ? points : undefined });
  }
  function pointerUp() {
    if (!dragRef.current) return;
    if (!dragRef.current.pan) {
      if (draft && draft.w >= 4 && draft.h >= 5 && (draft.mode !== 'freehand' || draft.points.length >= 3)) {
        interruptOcr(); dispatch({type:'set',id:activeId,key:'originalManuallyEdited',value:false}); setOriginalText(''); setSelection(draft); setAdjust(DEFAULT_ADJUST); setFont('auto'); setShowSelection(true);
      }
      else { setSelection(null); setMessage('请围住完整文字，留出少量背景。'); }
    }
    dragRef.current = null; setDraft(null);
  }
  function adopt() {
    if (!candidate || busy) return;
    interruptOcr(); dispatch({type:'adopt',id:activeId});
    setMessage('修改已采用，可继续编辑；支持撤销与重做。');
  }
  function undo() {
    if (busy || (!candidate && !history.length)) return;
    interruptOcr(); dispatch({type:'undo',id:activeId});
    setMessage(candidate ? '已撤销预览，可点击重做恢复。' : '已撤销上一次修改，可点击重做恢复。');
  }
  function redo() {
    if (busy || !future.length) return;
    interruptOcr(); dispatch({type:'redo',id:activeId}); setMessage('已恢复撤销的修改。');
  }
  function download(src, filename) { const anchor = document.createElement('a'); anchor.href = src; anchor.download = filename; anchor.click(); }
  function exportImage() { if (doc && !busy) download(candidate?.image || doc.base, doc.name.replace(/\.[^.]+$/, '') + '-已修改.png'); }
  function exportReport() {
    const blob = new Blob([JSON.stringify(candidate.report, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob); download(url, '精修检查报告.json'); setTimeout(() => URL.revokeObjectURL(url), 5000);
  }
  const activeSelection = draft || selection;
  const displayed = doc && (showOriginal ? doc.original : candidate?.image || doc.base);
  const report = candidate?.report;
  const tools = [['rectangle', SquareDashedMousePointer, '矩形框选'], ['freehand', PenTool, '自由画圈'], ['pan', Hand, '移动画布']];
  const sliders = [['x', '水平位置', -6, 6, .1, 'px'], ['y', '垂直位置', -6, 6, .1, 'px'], ['width', '字宽', .8, 1.2, .005, '×'], ['height', '字高', .8, 1.2, .005, '×'], ['angle', '角度', -5, 5, .1, '°'], ['blur', '边缘柔和', -.5, .8, .02, 'px'], ['darkness', '墨色浓度', .7, 1.3, .01, '×']];
  return <div className="app-shell" onDragOver={e => e.preventDefault()} onDrop={e => { e.preventDefault(); if (!busy) upload(e.dataTransfer.files); }}>
    <input ref={inputRef} type="file" multiple accept="image/png,image/jpeg,image/webp" className="visually-hidden" onChange={e => { upload(e.target.files); e.target.value = ''; }} />
    <header className="app-header"><div className="brand-mark"><ScanLine size={22} /></div><div className="brand"><strong>Retouch Desk<span>图片文字精修</span></strong><small>LOCAL IMAGE EDITOR</small></div><div className="header-spacer" /><div className={`connection ${connection}`}><i />{connection === 'ready' ? '本地 CPU 引擎' : connection === 'error' ? '引擎未连接' : '连接中'}</div><button className="icon-button help-button" onClick={() => setHelp(true)} title="使用说明" aria-label="使用说明"><CircleHelp size={19} /></button><button className="export-button" onClick={exportImage} disabled={!doc || busy}><ArrowDownToLine size={16} />导出 PNG</button></header>
    {workspace.tabs.length > 0 && <div className="document-strip"><div className="document-tabs" ref={tabListRef} role="tablist" aria-label="已打开的图片">{workspace.tabs.map((tab,index) => <div className={`document-tab ${tab.id === activeId ? 'active' : ''}`} key={tab.id}>
      <button id={`tab-${tab.id}`} role="tab" aria-selected={tab.id === activeId} aria-controls="image-workspace" className="document-tab-select" onClick={() => activateTab(tab.id)} title={tab.doc.name}><FileImage size={14}/><span>{tab.doc.name}</span>{(tab.candidate || tab.history.length>0) && <i className="tab-edited" aria-label="存在编辑结果"/>}{job?.tabId === tab.id && <LoaderCircle size={12} className="spinning"/>}</button>
      <button className="tab-close" onClick={() => closeTab(tab.id)} title={`关闭 ${tab.doc.name}`} aria-label={`关闭图片 ${index+1}：${tab.doc.name}`}><X size={13}/></button>
    </div>)}</div><button className="add-document" onClick={() => inputRef.current.click()} disabled={busy || opening} aria-label="添加图片" title="添加图片，可多选"><Plus size={17}/></button></div>}
    <main className="workspace" id="image-workspace" role={doc ? 'tabpanel' : undefined} aria-labelledby={doc ? `tab-${activeId}` : undefined}>
      <section className="editor-panel">
        <div className="editor-toolbar"><div className="tool-group">{tools.map(([id, Icon, label]) => <button key={id} className={tool === id ? 'tool-button selected' : 'tool-button'} onClick={() => setTool(id)} disabled={busy} title={label} aria-label={label}><Icon size={16} /><span>{label}</span></button>)}</div><div className="toolbar-separator" /><button className="icon-button" onClick={undo} disabled={busy || (!candidate && !history.length)} title="撤销（Ctrl+Z）" aria-label="撤销"><Undo2 size={17} /></button><button className="icon-button" onClick={redo} disabled={busy || !future.length} title="重做（Ctrl+Y / Ctrl+Shift+Z）" aria-label="重做"><Redo2 size={17} /></button><button className="cancel-selection-button" onClick={cancelSelection} disabled={!selection && !draft} title="取消框选（Esc）" aria-label="取消框选"><X size={14}/><span>取消框选</span></button><div className="header-spacer" />{doc && <><button className={`compare-button ${showOriginal ? 'active' : ''}`} onClick={() => setShowOriginal(v => !v)}><ArrowLeftRight size={14} />{showOriginal ? '正在看原图' : '对比原图'}</button><button className="icon-button" onClick={() => setShowSelection(v => !v)} title="显示或隐藏选区" aria-label="显示或隐藏选区"><Crosshair size={16} /></button></>}</div>
        <div className="canvas-viewport" ref={viewportRef}>
          {!doc ? <div className="empty-state"><span className="empty-index">01 / OPEN YOUR IMAGE</span><div className="empty-illustration"><div className="paper"><span>202<span className="old-digit">5</span><span className="new-digit">6</span></span><div /><div /></div><Crosshair size={31} /></div><h1>只改需要改的地方。</h1><p>从一张图片开始，找回字体、位置和纸张的质感。</p><button className="primary-button" onClick={() => inputRef.current.click()}><Plus size={18} />打开图片</button><span className="upload-note">PNG / JPEG / WEBP · 支持多选与拖入 · 最大 2400 万像素</span>{session?.sampleAvailable && <button className="sample-button" onClick={openSample}><FileImage size={14} />打开本次验收样图：2025 → 2026</button>}</div> : <div className="canvas-padding" style={{ minWidth: doc.width * zoom + 80, minHeight: doc.height * zoom + 64 }}><div className={`image-surface tool-${tool}`} ref={surfaceRef} style={{ width: doc.width * zoom, height: doc.height * zoom }} onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={pointerUp} onPointerCancel={() => { dragRef.current = null; setDraft(null); }}><img src={displayed} alt={showOriginal ? '原始图片' : '编辑预览'} draggable="false" /><svg className="selection-layer" viewBox={`0 0 ${doc.width} ${doc.height}`} aria-hidden="true">{showSelection && activeSelection && (activeSelection.mode === 'freehand' ? <polygon points={activeSelection.points.map(p => `${p.x},${p.y}`).join(' ')} /> : <rect x={activeSelection.x} y={activeSelection.y} width={activeSelection.w} height={activeSelection.h} />)}</svg>{showSelection && activeSelection && <div className="selection-label" style={{ left: activeSelection.x * zoom, top: activeSelection.y * zoom - 24 }}>{draft ? '选择区域' : `${Math.round(activeSelection.w)} × ${Math.round(activeSelection.h)} px`}</div>}</div></div>}
        </div>
        <div className="canvas-status"><span>{doc ? <><FileImage size={12} /><span className="filename" title={doc.name}>{doc.name}</span><b>{doc.width} × {doc.height}</b></> : <><ShieldCheck size={13} />本地处理 · 图片不上传</>}</span><div className="zoom-controls"><button className="icon-button" disabled={!doc} onClick={() => setZoom(z => clamp(z / 1.25, .15, 12))} aria-label="缩小"><ZoomOut size={14} /></button><span>{Math.round(zoom * 100)}%</span><button className="icon-button" disabled={!doc} onClick={() => setZoom(z => clamp(z * 1.25, .15, 12))} aria-label="放大"><ZoomIn size={14} /></button><button className="icon-button" disabled={!doc} onClick={() => setZoom(fitZoom)} aria-label="适应画布" title="适应画布"><Maximize2 size={14} /></button></div></div>
        <section className={`inspection-panel ${candidate ? 'has-result' : ''}`}><div className="section-caption"><span>DETAIL INSPECTION</span><strong>局部放大检查</strong>{candidate && <button className="text-button" onClick={exportReport}>导出检查报告</button>}</div>{candidate ? <div className="crop-grid">{[['originalCrop', '修改前', 'ORIGINAL'], ['reconstructionCrop', '原字重建', 'RECONSTRUCTION'], ['resultCrop', '修改后', 'RESULT']].map(([key, label, code]) => <figure key={key}><div className="crop-image"><img src={candidate[key]} alt={label} /></div><figcaption><span>{label}</span><small>{code}</small></figcaption></figure>)}</div> : <div className="inspection-placeholder"><Move size={19} /><p>生成预览后，在这里比较原图、原字重建和修改结果。</p><span>先把原来的字画得像，再替换成新的字。</span></div>}</section>
      </section>
      <aside className="inspector"><div className="inspector-heading"><div><span className="eyebrow">LOCAL PRECISION / 05</span><h2>文字精修</h2></div><Cpu size={23} /></div><div className="inspector-content">
        <div className="step-label"><span>01</span>选择图片与区域</div><button className="open-image-button" onClick={() => inputRef.current.click()} disabled={busy || opening}><FolderOpen size={15} />{opening ? '正在打开图片…' : doc ? '添加更多图片' : '打开本地图片'}<Upload size={14} /></button>{session?.sampleAvailable && doc && <button className="text-button sample-inline" onClick={openSample} disabled={busy}>重新打开验收样图</button>}<div className={`selection-summary ${selection ? 'ready' : ''}`}><Crosshair size={15} /><span>{selection ? `已选 ${Math.round(selection.w)} × ${Math.round(selection.h)} px · ${selection.mode === 'freehand' ? '自由画圈' : '矩形框选'}` : '框住完整文字，留少量背景'}</span>{selection && <button className="icon-button" disabled={busy} onClick={cancelSelection} title="取消框选（Esc）" aria-label="清除选区"><X size={13} /></button>}</div>
        <div className="step-label"><span>02</span>输入原文与新文字</div><label className="field-label" htmlFor="original-text">选区内原文字<small>用于重建与字体匹配</small></label><input id="original-text" className="text-input original-input" type="text" inputMode="text" autoComplete="off" autoCapitalize="off" spellCheck={false} value={originalText} maxLength={40} disabled={busy} onCompositionStart={() => { manualTextRevision.current++; dispatch({type:'set',id:activeId,key:'originalManuallyEdited',value:true}); }} onChange={e => { manualTextRevision.current++; dispatch({type:'set',id:activeId,key:'originalManuallyEdited',value:true}); changeSetting(setOriginalText, e.target.value); }} placeholder="框选后自动识别，也可手动输入" aria-describedby="ocr-status" />
        <div id="ocr-status" className={`ocr-status ${ocr?.status || 'idle'} ${ocr?.needsReview ? 'needs-review' : ''}`} role="status" aria-live="polite">
          {ocr?.status === 'running' ? <span><LoaderCircle size={12} className="spinning" />正在本地识别，可先手动输入…</span> : <span>{ocr?.status === 'done' ? `已识别「${ocr.text}」 · 识别评分 ${(Math.floor(ocr.confidence * 1000) / 10).toFixed(1)}% · ${ocr.seconds}s。${ocr.applied ? '可手动修改。' : '已保留你的手动输入。'}` : ocr?.message || '矩形框选与自由画圈后自动识别，结果由你核对。'}</span>}
          {ocr?.needsReview && ocr?.text && <span className="ocr-review">{ocr.message}{ocr.alternatives?.length > 0 && ` 其他候选：${ocr.alternatives.join(' / ')}`}</span>}
          <div className="ocr-actions">{selection && <button className="text-button" disabled={busy || ocr?.status === 'running'} onClick={() => setOcrRetry(n => n + 1)}>重新识别</button>}{ocr?.text && !ocr.applied && ocr.text.length <= 40 && <button className="text-button" disabled={busy} onClick={() => { manualTextRevision.current++; dispatch({type:'set',id:activeId,key:'originalManuallyEdited',value:true}); changeSetting(setOriginalText, ocr.text); setOcr(prev => ({ ...prev, applied: true })); }}>使用识别结果</button>}</div>
        </div><label className="field-label" htmlFor="replacement-text">替换为</label><input id="replacement-text" className="text-input replacement-input" type="text" inputMode="text" autoComplete="off" autoCapitalize="off" spellCheck={false} value={replacement} maxLength={40} disabled={busy} onChange={e => changeSetting(setReplacement, e.target.value)} placeholder="例如：2026" /><p className="field-hint">请核对识别结果；以你最终填写的原文和新文字为准。同长度替换时，只重绘变化字符。</p>
        <div className="step-label"><span>03</span>匹配与精调</div><label className="field-label" htmlFor="font-select">字体策略</label><div className="select-wrap"><select id="font-select" value={font} disabled={busy} onChange={e => changeSetting(setFont, e.target.value)}><option value="auto">自动检索本机字体</option>{session?.fonts.map(f => <option value={f.key} key={f.key}>{f.name}</option>)}</select><ChevronDown size={14} /></div>{report && <div className="font-result"><Check size={13} /><span>当前候选：{report.font}</span></div>}
        <label className="field-label" htmlFor="contrast-select">文字与背景</label><div className="select-wrap"><select id="contrast-select" value={contrast} disabled={busy} onChange={e => changeSetting(setContrast, e.target.value)}><option value="auto">自动判断文字深浅</option><option value="dark">深色文字 / 浅色背景</option><option value="light">浅色文字 / 深色背景</option></select><ChevronDown size={14} /></div>
        <button className="adjust-toggle" onClick={() => setShowAdjust(v => !v)} aria-expanded={showAdjust}><span><Move size={14} />精细调整</span><ChevronDown size={14} className={showAdjust ? 'rotated' : ''} /></button>{showAdjust && <div className="adjustments">{sliders.map(([key, label, min, max, step, unit]) => <label className="slider-field" key={key}><span>{label}<output>{Number(adjust[key]).toFixed(key === 'width' || key === 'height' ? 3 : 2)}{unit}</output></span><input type="range" min={min} max={max} step={step} value={adjust[key]} disabled={busy} onChange={e => { setAdjust(prev => ({ ...prev, [key]: Number(e.target.value) })); invalidate(); }} /></label>)}<button className="text-button" disabled={busy} onClick={() => { setAdjust(DEFAULT_ADJUST); invalidate(); }}><RotateCcw size={12} />重置微调</button><p className="field-hint">调整后需重新生成预览，修改始终从当前底图开始。</p></div>}
        {report && <div className="report-card"><div className="report-title"><ShieldCheck size={15} /><strong>检查结果</strong><span>{report.seconds}s</span></div><dl><div><dt>文字模式</dt><dd>{report.textColorMode}</dd></div><div><dt>选区外变化</dt><dd className={report.outsideChangedPixels === 0 ? 'good' : 'bad'}>{report.outsideChangedPixels} 像素</dd></div><div><dt>实际修改</dt><dd>{report.changedPixels} 像素 / {report.changedCharacters} 字符</dd></div><div><dt>原字墨迹误差</dt><dd>{report.sourceInkRmse} / 255</dd></div><div><dt>角度 / 模糊</dt><dd>{report.angle}° / {report.blur}px</dd></div></dl><p>重建误差越小越接近原字；它不是无痕概率。请核对新字与观感。</p>{report.warnings.map((warning, i) => <p className="warning-text" key={i}>{warning}</p>)}</div>}
        {!report && <div className="engine-note"><ShieldCheck size={17} /><div><strong>CPU 本地重建</strong><p>拟合原字形、倾斜与清晰度，再修复背景并合成。支持浅底深字和深底浅字的单行印刷文字；未知字体与复杂背景仍需人工检查。</p></div></div>}
      </div><div className="inspector-footer">{error && <div className="error-message" role="alert"><X size={15} /><span>{error}</span></div>}{busy ? <div className="job-progress" role="status"><div><LoaderCircle size={15} className="spinning" /><span>{job.tabId !== activeId ? `${workspace.tabs.find(tab => tab.id === job.tabId)?.doc.name || '另一张图片'}：` : ''}{job.message}</span><button className="text-button" onClick={cancelJob}>取消</button></div><progress max="1" value={job.progress || .02} /></div> : <button className="generate-button" onClick={generate} disabled={!doc || !selection || !originalText.trim() || !replacement.trim() || originalText === replacement || connection !== 'ready' || ocr?.status === 'running'}><ScanLine size={17} />{candidate ? '重新生成预览' : '生成精修预览'}<span>↗</span></button>}<button className="adopt-button" onClick={adopt} disabled={!candidate || busy}><Check size={16} />采用这次修改</button><span className="footer-note">预览不会覆盖原图 · PNG 保留原尺寸</span></div></aside>
    </main><footer className="app-footer"><span>RET / 05</span><span>本地处理 · 细节可控</span><span>RETOUCH DESK 0.5 · OFFLINE</span></footer>
    {message && <div className="toast" role="status"><Check size={15} />{message}</div>}
    {error && !doc && <div className="global-error" role="alert">{error}<button onClick={() => setError('')} aria-label="关闭错误"><X size={14} /></button></div>}
    {connection === 'error' && <div className="connection-error" role="alert">本地处理服务未连接。请双击「一键启动.bat」或打开打包后的应用。</div>}
    {help && <div className="modal-backdrop" onClick={() => setHelp(false)}><section className="help-modal" role="dialog" aria-modal="true" aria-labelledby="help-title" onClick={e => e.stopPropagation()}><button className="icon-button modal-close" onClick={() => setHelp(false)} aria-label="关闭说明"><X size={19} /></button><span className="eyebrow">A SMALL GUIDE</span><h2 id="help-title">把细节交还给你。</h2><ol><li>打开图片，框住完整的一处文字。例如，完整圈住“2025”。</li><li>框选后会自动识别原文字；核对或手动修正，再填写新文字。</li><li>生成预览后，对比原字重建和修改结果。原字都不像时，先调整字体与选区。</li><li>必要时切换字体、微调位置与清晰度，再生成。</li><li>顶部标签可切换多张图片；取消框选可点击工具栏或按 Esc。采用后支持撤销与重做；导出 PNG 保存当前图片。</li></ol><p>此版本使用本机字体和 CPU 处理，不会上传图片；不保证任意字体、复杂背景或弯曲文字的自动还原。一次处理一行文字。</p><button className="primary-button" onClick={() => setHelp(false)}>开始使用</button></section></div>}
  </div>;
}

createRoot(document.getElementById('root')).render(<App />);
