import { useState, useEffect } from 'react'
import { listFloors, createFloor, deleteFloor, getFloorGraph } from '../../api/staffApi'

// ── Floor Map Panel ───────────────────────────────────────────
// Renders floor list + SVG graph viewer + upload form
export default function FloorMapPanel({ floors, onRefresh }) {
  const [selected,    setSelected]    = useState(null)   // floor object
  const [graph,       setGraph]       = useState(null)
  const [uploading,   setUploading]   = useState(false)
  const [floorName,   setFloorName]   = useState('')
  const [imageFile,   setImageFile]   = useState(null)
  const [deleting,    setDeleting]    = useState(null)
  const [graphError,  setGraphError]  = useState('')

  // Load graph when floor selected
  useEffect(() => {
    if (!selected) { setGraph(null); return }
    setGraphError('')
    getFloorGraph(selected.id || selected.floor_id)
      .then(data => setGraph(data.graph || data))
      .catch(e => setGraphError(e.message))
  }, [selected])

  async function handleCreate(e) {
    e.preventDefault()
    if (!floorName.trim()) return
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append('name', floorName)
      if (imageFile) fd.append('image', imageFile)
      await createFloor(fd)
      setFloorName('')
      setImageFile(null)
      await onRefresh()
    } catch (err) {
      alert('Create failed: ' + err.message)
    } finally { setUploading(false) }
  }

  async function handleDelete(floor) {
    if (!confirm(`Delete floor "${floor.name}"? This is irreversible.`)) return
    setDeleting(floor.id)
    try {
      await deleteFloor(floor.id || floor.floor_id)
      if (selected?.id === floor.id) setSelected(null)
      await onRefresh()
    } catch (err) {
      alert('Delete failed: ' + err.message)
    } finally { setDeleting(null) }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
      {/* Left: floor list + create form */}
      <div className="space-y-4">
        <h2 className="text-base font-semibold text-white">Floors</h2>

        {/* Create form */}
        <form onSubmit={handleCreate} className="card space-y-3">
          <h3 className="text-sm font-semibold text-slate-300">Add New Floor</h3>
          <div>
            <label className="label">Floor Name</label>
            <input
              id="input-floor-name"
              className="input"
              placeholder="Ground Floor"
              value={floorName}
              onChange={e => setFloorName(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="label">Floor Plan Image (optional)</label>
            <input
              id="input-floor-image"
              type="file"
              accept="image/*"
              className="text-xs text-slate-400 file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-slate-700 file:text-slate-300 hover:file:bg-slate-600 cursor-pointer w-full"
              onChange={e => setImageFile(e.target.files[0] || null)}
            />
          </div>
          <button
            id="btn-create-floor"
            type="submit"
            disabled={uploading}
            className="btn-primary w-full disabled:opacity-50"
          >
            {uploading ? 'Creating…' : '+ Create Floor'}
          </button>
        </form>

        {/* Floor list */}
        <div className="space-y-2">
          {floors.length === 0 && (
            <p className="text-slate-500 text-sm text-center py-4">No floors yet</p>
          )}
          {floors.map(f => (
            <div
              key={f.id}
              className={`card-sm cursor-pointer transition-all hover:border-slate-600 ${selected?.id === f.id ? 'border-brand-600/50 bg-brand-950/20' : ''}`}
              onClick={() => setSelected(f)}
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-white truncate">{f.name}</p>
                  <p className="text-xs text-slate-400 font-mono">{f.floor_id || f.id?.slice(0, 8)}</p>
                </div>
                <button
                  id={`btn-delete-floor-${f.id}`}
                  onClick={e => { e.stopPropagation(); handleDelete(f) }}
                  disabled={deleting === f.id}
                  className="text-slate-500 hover:text-red-400 transition-colors text-xs px-2 py-1 rounded"
                >
                  {deleting === f.id ? '…' : '🗑'}
                </button>
              </div>
              {f.image_url && (
                <img
                  src={`http://localhost:8001${f.image_url}`}
                  alt="floor plan"
                  className="mt-2 rounded-lg w-full h-20 object-cover opacity-60"
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Right: SVG graph viewer */}
      <div className="lg:col-span-2">
        <h2 className="text-base font-semibold text-white mb-3">
          {selected ? `Graph: ${selected.name}` : 'Select a floor to view its graph'}
        </h2>
        {graphError && (
          <div className="card-sm text-red-400 text-sm">{graphError}</div>
        )}
        {selected && !graphError && (
          graph
            ? <GraphCanvas graph={graph} />
            : <div className="card flex items-center justify-center h-64 text-slate-400 text-sm">Loading graph…</div>
        )}
        {!selected && (
          <div className="card flex flex-col items-center justify-center h-64 text-slate-500">
            <span className="text-4xl mb-3">🗺️</span>
            <p className="text-sm">Select a floor from the list</p>
          </div>
        )}
      </div>
    </div>
  )
}


// ── SVG Graph Canvas ──────────────────────────────────────────
const NODE_COLORS = {
  room:      '#3b82f6',
  corridor:  '#6366f1',
  stairwell: '#f59e0b',
  stairs:    '#f59e0b',
  exit:      '#10b981',
  default:   '#94a3b8',
}

function GraphCanvas({ graph }) {
  const nodes  = graph?.nodes || []
  const edges  = graph?.edges || []

  if (nodes.length === 0) {
    return (
      <div className="card flex items-center justify-center h-64 text-slate-400 text-sm">
        No nodes in graph
      </div>
    )
  }

  // Normalise positions to [0, 1] then scale to canvas
  const W = 720, H = 420, PAD = 40, R = 18
  const xs = nodes.map(n => n.x ?? n.position?.x ?? Math.random() * W)
  const ys = nodes.map(n => n.y ?? n.position?.y ?? Math.random() * H)
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const rangeX = maxX - minX || 1, rangeY = maxY - minY || 1

  const scale = (v, min, range, dim) =>
    PAD + ((v - min) / range) * (dim - PAD * 2)

  const posMap = {}
  nodes.forEach((n, i) => {
    posMap[n.id] = {
      cx: scale(xs[i], minX, rangeX, W),
      cy: scale(ys[i], minY, rangeY, H),
    }
  })

  return (
    <div className="card p-3 overflow-auto">
      <svg width={W} height={H} className="rounded-xl bg-slate-900/60 w-full" viewBox={`0 0 ${W} ${H}`}>
        {/* Edges */}
        {edges.map((e, i) => {
          const from = posMap[e.from || e.from_node]
          const to   = posMap[e.to   || e.to_node]
          if (!from || !to) return null
          return (
            <line
              key={i}
              x1={from.cx} y1={from.cy}
              x2={to.cx}   y2={to.cy}
              stroke="#334155" strokeWidth="2"
            />
          )
        })}

        {/* Nodes */}
        {nodes.map(n => {
          const pos   = posMap[n.id]
          const color = NODE_COLORS[n.type] || NODE_COLORS.default
          if (!pos) return null
          return (
            <g key={n.id}>
              <circle
                cx={pos.cx} cy={pos.cy} r={R}
                fill={color} fillOpacity="0.25"
                stroke={color} strokeWidth="2"
              />
              <text
                x={pos.cx} y={pos.cy + 1}
                textAnchor="middle" dominantBaseline="middle"
                fill="white" fontSize="9" fontWeight="600"
              >
                {(n.label || n.id).slice(0, 10)}
              </text>
              <text
                x={pos.cx} y={pos.cy + R + 10}
                textAnchor="middle"
                fill={color} fontSize="8" opacity="0.8"
              >
                {n.type}
              </text>
            </g>
          )
        })}
      </svg>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 mt-3">
        {Object.entries(NODE_COLORS).filter(([k]) => k !== 'default').map(([type, color]) => (
          <div key={type} className="flex items-center gap-1.5 text-xs text-slate-400">
            <span className="w-3 h-3 rounded-full" style={{ background: color, opacity: 0.8 }} />
            {type}
          </div>
        ))}
      </div>
    </div>
  )
}
