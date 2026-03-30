import type { NodeType } from '../types'
import type { DesignerTool } from '../hooks/useDesignerState'

interface DesignerNodePaletteProps {
  selectedTool: DesignerTool
  onSelectTool: (tool: DesignerTool) => void
}

interface ToolEntry {
  tool: DesignerTool
  label: string
  icon: string // single unicode/text char
  color: string
  shortcut: string
}

const TOOLS: ToolEntry[] = [
  { tool: 'select', label: 'Select', icon: '\u2316', color: '#cdd6f4', shortcut: 'V' },
  { tool: 'edge',   label: 'Edge',   icon: '\u2014', color: '#cdd6f4', shortcut: 'E' },
  { tool: 'zone',   label: 'Zone',   icon: '\u25A1', color: '#cdd6f4', shortcut: 'Z' },
]

const NODE_TYPES: ToolEntry[] = [
  { tool: 'shelf',  label: 'Shelf',   icon: '\u25A0', color: '#89b4fa', shortcut: 'S' },
  { tool: 'aisle',  label: 'Aisle',   icon: '\u25CF', color: '#6c7086', shortcut: 'A' },
  { tool: 'charge', label: 'Charge',  icon: '\u26A1', color: '#a6e3a1', shortcut: 'C' },
  { tool: 'pick',   label: 'Pick',    icon: '\u25B2', color: '#f9e2af', shortcut: 'P' },
  { tool: 'drop',   label: 'Drop',    icon: '\u25BC', color: '#fab387', shortcut: 'D' },
  { tool: 'hub',    label: 'Hub',     icon: '\u2B22', color: '#cba6f7', shortcut: 'H' },
]

export function DesignerNodePalette({ selectedTool, onSelectTool }: DesignerNodePaletteProps) {
  return (
    <div className="bg-panel border-r border-border flex flex-col gap-1 p-2 w-full h-full overflow-y-auto">
      <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-1">Tools</h3>
      {TOOLS.map((t) => (
        <PaletteButton key={t.tool} entry={t} active={selectedTool === t.tool} onClick={() => onSelectTool(t.tool)} />
      ))}

      <div className="border-t border-border my-2" />

      <h3 className="text-[10px] font-semibold text-muted uppercase tracking-wider mb-1">Nodes</h3>
      {NODE_TYPES.map((t) => (
        <PaletteButton key={t.tool} entry={t} active={selectedTool === t.tool} onClick={() => onSelectTool(t.tool as NodeType)} />
      ))}
    </div>
  )
}

function PaletteButton({ entry, active, onClick }: { entry: ToolEntry; active: boolean; onClick: () => void }) {
  return (
    <button
      className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs transition-colors w-full text-left ${
        active
          ? 'bg-accent/20 border border-accent text-gray-100'
          : 'border border-transparent text-muted hover:text-gray-200 hover:bg-surface'
      }`}
      onClick={onClick}
      title={`${entry.label} (${entry.shortcut})`}
    >
      <span className="text-base w-5 text-center" style={{ color: entry.color }}>
        {entry.icon}
      </span>
      <span className="flex-1">{entry.label}</span>
      <span className="text-[9px] text-muted opacity-60">{entry.shortcut}</span>
    </button>
  )
}
