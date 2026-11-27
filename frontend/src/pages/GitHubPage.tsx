import { useMemo, useRef, useState } from 'react'
import { AlertCircle, ArrowUpRight, Check, ChevronDown, ExternalLink, GitFork, Github, LoaderCircle, LockKeyhole, RefreshCw, Star } from 'lucide-react'
import { fetchGitHubFiles, fetchGitHubRepository } from '../services/api'
import type { GitHubFiles, GitHubRepository } from '../types'

export function normalizeGitHubUrl(value: string): string | null {
  if (!value || value.length > 2048) return null
  try {
    const trimmed = value.trim()
    const parsed = new URL(trimmed)
    const authority = trimmed.match(/^https:\/\/([^/?#]+)/i)?.[1]
    if (parsed.protocol !== 'https:' || parsed.hostname !== 'github.com' || authority?.toLowerCase() !== 'github.com' || parsed.username || parsed.password || parsed.search || parsed.hash) return null
    const path = parsed.pathname.endsWith('/') ? parsed.pathname.slice(0, -1) : parsed.pathname
    const parts = path.startsWith('/') ? path.slice(1).split('/') : []
    if (parts.length !== 2 || parts.some(part => !part || part.includes('%'))) return null
    const [owner, repository] = parts
    if (!/^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$/.test(owner)) return null
    if (!/^[A-Za-z0-9_.-]+$/.test(repository) || repository === '.' || repository === '..') return null
    return `https://github.com/${owner}/${repository}`
  } catch {
    return null
  }
}

interface FileNode { name: string; path: string; children: Map<string, FileNode>; isFile: boolean }

function buildFileTree(paths: string[]): FileNode[] {
  const root = new Map<string, FileNode>()
  paths.forEach(path => {
    let current = root
    const parts = path.split('/').filter(Boolean)
    parts.forEach((part, index) => {
      let node = current.get(part)
      if (!node) {
        node = { name: part, path: parts.slice(0, index + 1).join('/'), children: new Map(), isFile: index === parts.length - 1 }
        current.set(part, node)
      }
      current = node.children
    })
  })
  return [...root.values()]
}

export default function GitHubPage() {
  const [url, setUrl] = useState('')
  const [repository, setRepository] = useState<GitHubRepository | null>(null)
  const [files, setFiles] = useState<GitHubFiles | null>(null)
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const busy = useRef(false)
  const tree = useMemo(() => buildFileTree(files?.python_files ?? []), [files])

  const updateUrl = (value: string) => {
    setUrl(value)
    setRepository(null)
    setFiles(null)
    setSelected(new Set())
    setError('')
  }

  const connect = async () => {
    if (busy.current) return
    const normalized = normalizeGitHubUrl(url)
    if (!normalized) {
      setRepository(null)
      setFiles(null)
      setSelected(new Set())
      setError('Enter a valid GitHub repository URL, such as https://github.com/owner/repository.')
      return
    }
    busy.current = true
    setLoading(true)
    setError('')
    setRepository(null)
    setFiles(null)
    setSelected(new Set())
    try {
      const repo = await fetchGitHubRepository(normalized)
      const fileList = await fetchGitHubFiles(normalized)
      setRepository(repo)
      setFiles(fileList)
      setUrl(repo.normalized_url)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not connect to this GitHub repository.')
    } finally {
      busy.current = false
      setLoading(false)
    }
  }

  const visibleFiles = files?.python_files ?? []
  const toggleFile = (path: string) => setSelected(current => {
    const next = new Set(current)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    return next
  })
  const selectAll = () => setSelected(new Set(visibleFiles))
  const clearSelection = () => setSelected(new Set())

  return <div className="page-stack github-page">
    <section className="page-intro github-intro"><div><div className="eyebrow"><span className="eyebrow-line" /> REPOSITORY BROWSER</div><h2>Connect a GitHub repository.</h2><p>Validate a repository and browse its Python file paths. Repository files are not downloaded or analyzed in this phase.</p></div><div className="github-safe-tag"><LockKeyhole size={14} /> Read-only metadata and paths</div></section>

    <section className="panel github-connect-panel" aria-label="Connect a GitHub repository">
      <label htmlFor="github-repository-url">Repository URL</label>
      <div className="github-connect-row"><div className="github-url-field"><Github size={16} /><input id="github-repository-url" value={url} onChange={event => updateUrl(event.target.value)} onKeyDown={event => { if (event.key === 'Enter') void connect() }} placeholder="https://github.com/owner/repository" disabled={loading} autoComplete="url" /></div><button className="button-primary" onClick={() => void connect()} disabled={loading}>{loading ? <><LoaderCircle size={15} className="spin" /> Connecting…</> : <><RefreshCw size={15} /> Connect repository</>}</button></div>
      <span className="github-input-hint">Public repositories are supported. Private repository access is disabled for this public service.</span>
      {error && <div className="form-error github-error" role="alert"><AlertCircle size={16} /><span>{error}</span></div>}
    </section>

    {loading && <div className="github-loading" role="status"><LoaderCircle size={17} className="spin" /> Connecting to GitHub and listing Python files…</div>}

    {repository && files && <>
      <section className="panel github-repository-panel" aria-label="Repository information">
        <div className="github-repo-top"><div className="github-repo-mark"><Github size={19} /></div><div className="github-repo-title"><span>{repository.owner} <b>/</b></span><h3>{repository.name}</h3></div><a className="github-open-link" href={repository.html_url} target="_blank" rel="noopener noreferrer">Open on GitHub <ExternalLink size={13} /></a></div>
        <p className="github-description">{repository.description || 'No repository description provided.'}</p>
        <div className="github-repo-meta"><span><span className={`repo-visibility ${repository.private ? 'is-private' : ''}`}><i />{repository.private ? 'Private' : 'Public'}</span></span><span>Default branch <strong>{repository.default_branch}</strong></span>{repository.stargazers_count !== null && <span><Star size={13} /> <strong>{repository.stargazers_count.toLocaleString()}</strong> stars</span>}{repository.fork && <span><GitFork size={13} /> Fork</span>}{repository.visibility && repository.visibility.toLowerCase() !== (repository.private ? 'private' : 'public') && <span>Visibility <strong>{repository.visibility}</strong></span>}{repository.updated_at && <span>Updated <strong>{formatUpdated(repository.updated_at)}</strong></span>}</div>
      </section>

      <section className="panel github-files-panel" aria-label="Python file browser">
        <div className="github-files-heading"><div><h3>Python files</h3><p>{files.total_python_files === null ? `${files.python_files.length} returned in an incomplete tree` : `${files.total_python_files.toLocaleString()} Python ${files.total_python_files === 1 ? 'file' : 'files'} in ${repository.full_name}`}</p></div><span className="github-file-count">{visibleFiles.length.toLocaleString()} shown</span></div>
        {(files.truncated || files.file_list_limited) && <div className="github-truncation" role="status"><AlertCircle size={15} /><span>{files.limitation || 'The returned file list is limited and may be incomplete.'}</span></div>}
        <div className="github-selection-toolbar"><span><Check size={13} /> {selected.size} selected</span><div><button className="quiet-link" onClick={selectAll} disabled={!visibleFiles.length}>Select all visible</button><button className="quiet-link" onClick={clearSelection} disabled={!selected.size}>Clear selection</button></div></div>
        {visibleFiles.length ? <div className="github-file-tree" role="tree" aria-label="Repository Python files">{sortNodes(tree).map(node => <TreeBranch key={node.path} node={node} selected={selected} onToggle={toggleFile} />)}</div> : <div className="github-files-empty"><div className="empty-icon"><Github size={19} /></div><strong>No Python files found</strong><span>This repository tree contains no visible files ending in .py.</span></div>}
        <div className="github-files-footer">Selection prepares for a future phase. No file contents are fetched or analyzed.</div>
      </section>
    </>}

    {!repository && !loading && !error && <div className="github-empty-state"><div className="github-empty-icon"><Github size={20} /></div><strong>Connect a repository to get started</strong><span>Enter a GitHub repository URL to view its details and Python file tree.</span><ArrowUpRight size={15} /></div>}
  </div>
}

function TreeBranch({ node, selected, onToggle, depth = 0 }: { node: FileNode; selected: Set<string>; onToggle: (path: string) => void; depth?: number }) {
  if (node.isFile) return <label className="github-file-row" role="treeitem" style={{ paddingLeft: `${12 + depth * 17}px` }}><input type="checkbox" aria-label={`Select ${node.path}`} checked={selected.has(node.path)} onChange={() => onToggle(node.path)} /><code>{node.path}</code></label>
  return <div className="github-folder" role="group" aria-label={`${node.name} directory`}><div className="github-folder-label" style={{ paddingLeft: `${9 + depth * 17}px` }}><ChevronDown size={13} /><span>{node.name}</span></div>{sortNodes([...node.children.values()]).map(child => <TreeBranch key={child.path} node={child} selected={selected} onToggle={onToggle} depth={depth + 1} />)}</div>
}

function sortNodes(nodes: FileNode[]) {
  return nodes.slice().sort((left, right) => Number(left.isFile) - Number(right.isFile) || left.name.localeCompare(right.name))
}

function formatUpdated(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}
