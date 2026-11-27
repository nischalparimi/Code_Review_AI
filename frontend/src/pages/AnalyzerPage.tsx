import { useRef, useState } from 'react'
import { AlertCircle, ArrowLeft, Check, Code2, FileCode2, FileUp, LoaderCircle, RotateCcw, Sparkles, Upload, X } from 'lucide-react'
import type { AnalysisSession } from '../types'
import { analyzeFile, analyzeSource } from '../services/api'
import ResultsView from '../components/findings/ResultsView'

const SAMPLE = `import os\n\nAPI_KEY = "sample-secret-value"\n\ndef evaluate_input(user_input):\n    # TODO: replace this dynamic evaluation\n    return eval(user_input)\n`;

function readUploadedSource(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result ?? ''))
    reader.onerror = () => reject(reader.error ?? new Error('Could not read the selected file.'))
    reader.readAsText(file)
  })
}

export default function AnalyzerPage({ session, onAnalyzed, onNewAnalysis }: { session: AnalysisSession | null; onAnalyzed: (filename: string, result: Awaited<ReturnType<typeof analyzeSource>>, sourceCode: string) => void; onNewAnalysis: () => void }) {
  const [mode, setMode] = useState<'paste' | 'upload'>('paste')
  const [source, setSource] = useState('')
  const [filename, setFilename] = useState('main.py')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  if (session) return <div className="page-stack"><div className="results-toolbar"><button className="button-secondary" onClick={onNewAnalysis}><ArrowLeft size={15} /> New analysis</button><span className="result-source"><Check size={14} /> Live backend result · {session.filename}</span></div><ResultsView result={session.result} filename={session.filename} sourceCode={session.source_code ?? ''} compact /></div>

  const acceptFile = (candidate?: File) => {
    if (!candidate) return
    if (!candidate.name.toLowerCase().endsWith('.py')) { setError('Choose a Python source file with a .py extension.'); return }
    if (candidate.size > 1_048_576) { setError('The file exceeds the 1 MiB analysis limit.'); return }
    setError(''); setFile(candidate)
  }
  const submit = async () => {
    setError('')
    if (mode === 'upload' && !file) { setError('Select a .py file before starting analysis.'); return }
    if (mode === 'paste' && !source.trim()) { setError('Paste Python source before starting analysis.'); return }
    const activeName = mode === 'upload' ? file!.name : filename.trim()
    if (!activeName.toLowerCase().endsWith('.py')) { setError('The filename must end in .py.'); return }
    setLoading(true)
    try {
      const submittedSource = mode === 'upload' ? await readUploadedSource(file!) : source
      const result = mode === 'upload' ? await analyzeFile(file!) : await analyzeSource(source, activeName)
      onAnalyzed(result.files[0]?.file ?? activeName, result, submittedSource)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Analysis failed. Please try again.')
    } finally { setLoading(false) }
  }
  const clear = () => { setSource(''); setError('') }

  return <div className="page-stack analyzer-layout">
    <section className="analyzer-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> PYTHON STATIC ANALYSIS</div><h2>Review your code.</h2><p>Run the existing AST rule set against a file or a code snippet.</p></div><div className="safe-tag"><ShieldIcon /> Code is analyzed, never executed</div></section>
    <section className="panel analyzer-panel"><div className="analyzer-tabs" role="tablist" aria-label="Source input mode"><button role="tab" aria-selected={mode === 'paste'} className={mode === 'paste' ? 'selected' : ''} onClick={() => { setMode('paste'); setError('') }}><Code2 size={16} /> Paste code</button><button role="tab" aria-selected={mode === 'upload'} className={mode === 'upload' ? 'selected' : ''} onClick={() => { setMode('upload'); setError('') }}><Upload size={15} /> Upload file</button></div>
      {mode === 'paste' ? <div className="editor-section"><div className="editor-toolbar"><label className="filename-field"><FileCode2 size={15} /><input value={filename} onChange={event => setFilename(event.target.value)} aria-label="Python filename" /></label><div className="editor-actions"><span className="language-chip">Python</span><button className="text-button" onClick={() => { setSource(SAMPLE); setError('') }}><Sparkles size={14} /> Load sample</button><button className="text-button" onClick={clear}><RotateCcw size={14} /> Clear</button></div></div><textarea className="code-editor" value={source} onChange={event => setSource(event.target.value)} spellCheck={false} placeholder={'# Paste Python code here…\ndef greet(name):\n    return f"Hello, {name}"'} aria-label="Python source code" /><div className="editor-status"><span><i className="language-dot" /> Python</span><span>{new TextEncoder().encode(source).length.toLocaleString()} / 1,048,576 bytes</span></div></div> : <div className="upload-section">
        {!file ? <button className={`drop-zone ${dragging ? 'dragging' : ''}`} onClick={() => inputRef.current?.click()} onDragOver={event => { event.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); acceptFile(event.dataTransfer.files[0]) }}><input ref={inputRef} type="file" accept=".py,text/x-python,text/plain" hidden onChange={event => acceptFile(event.target.files?.[0])} /><span className="upload-glyph"><FileUp size={21} /></span><strong>Drop your Python file here</strong><span>or <b>browse files</b> from your computer</span><small>PYTHON SOURCE · MAXIMUM 1 MB</small></button> : <div className="selected-file"><div className="selected-file-icon"><FileCode2 size={20} /></div><div className="selected-file-meta"><strong>{file.name}</strong><span>{(file.size / 1024).toFixed(file.size < 1024 ? 0 : 1)} KB · Python source</span></div><button className="icon-button" aria-label="Remove selected file" onClick={() => setFile(null)}><X size={17} /></button><button className="button-secondary small" onClick={() => inputRef.current?.click()}>Replace</button><input ref={inputRef} type="file" accept=".py,text/x-python,text/plain" hidden onChange={event => acceptFile(event.target.files?.[0])} /></div>}
        <div className="upload-hint"><ShieldIcon /><span>Files are sent to your local FastAPI backend and removed after analysis.</span></div>
      </div>}
      {error && <div className="form-error" role="alert"><AlertCircle size={16} /><span>{error}</span></div>}
      <div className="analyze-footer"><div className="analysis-note"><span className="backend-mini-dot" /> Uses 14 registered analyzer rules</div><button className="button-primary analyze-button" onClick={submit} disabled={loading}>{loading ? <><LoaderCircle size={16} className="spin" /> Analyzing…</> : <><Code2 size={16} /> Analyze code <span className="button-kbd">↵</span></>}</button></div>
    </section>
    <div className="privacy-footnote"><ShieldIcon /><span>Static analysis only. Your code is not run or persisted by this interface.</span></div>
  </div>
}

function ShieldIcon() { return <span className="shield-check"><Check size={11} /></span> }
