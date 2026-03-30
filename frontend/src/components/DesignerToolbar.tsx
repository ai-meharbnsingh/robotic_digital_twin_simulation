import { useCallback, useRef, useState } from 'react'
import type { DesignerValidation, WarehouseConfig } from '../types'

interface DesignerToolbarProps {
  gridSpacing: number
  onGridSpacingChange: (spacing: number) => void
  canUndo: boolean
  canRedo: boolean
  onUndo: () => void
  onRedo: () => void
  onAutoEdges: () => void
  onValidate: () => Promise<DesignerValidation>
  onExport: () => Promise<{ saved: boolean; path?: string; error?: string }>
  onExportJson: () => WarehouseConfig
  onImportJson: (config: WarehouseConfig) => void
  onLoadTemplate: (template: string) => void
}

export function DesignerToolbar({
  gridSpacing,
  onGridSpacingChange,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onAutoEdges,
  onValidate,
  onExport,
  onExportJson,
  onImportJson,
  onLoadTemplate,
}: DesignerToolbarProps) {
  const [validationResult, setValidationResult] = useState<DesignerValidation | null>(null)
  const [exportStatus, setExportStatus] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleValidate = useCallback(async () => {
    const result = await onValidate()
    setValidationResult(result)
    // Auto-clear after 5 seconds
    setTimeout(() => setValidationResult(null), 5000)
  }, [onValidate])

  const handleExportServer = useCallback(async () => {
    setExportStatus('Exporting...')
    const result = await onExport()
    if (result.saved) {
      setExportStatus(`Saved: ${result.path ?? 'OK'}`)
    } else {
      setExportStatus(`Error: ${result.error ?? 'Unknown'}`)
    }
    setTimeout(() => setExportStatus(null), 4000)
  }, [onExport])

  const handleExportDownload = useCallback(() => {
    const config = onExportJson()
    const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `warehouse_${Date.now()}.json`
    a.click()
    URL.revokeObjectURL(url)
  }, [onExportJson])

  const handleImportFile = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0]
      if (!file) return
      const reader = new FileReader()
      reader.onload = () => {
        try {
          const config = JSON.parse(reader.result as string) as WarehouseConfig
          onImportJson(config)
        } catch {
          setExportStatus('Invalid JSON file')
          setTimeout(() => setExportStatus(null), 3000)
        }
      }
      reader.readAsText(file)
      // Reset input so same file can be re-imported
      e.target.value = ''
    },
    [onImportJson],
  )

  return (
    <div className="bg-panel border-b border-border px-3 py-1.5 flex items-center gap-2 flex-wrap">
      {/* Template loader */}
      <select
        className="bg-surface border border-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-accent"
        defaultValue=""
        onChange={(e) => {
          if (e.target.value) onLoadTemplate(e.target.value)
          e.target.value = ''
        }}
      >
        <option value="" disabled>
          Load template...
        </option>
        <option value="template_small">Small Warehouse</option>
        <option value="template_medium">Medium Warehouse</option>
        <option value="template_large">Large Warehouse</option>
      </select>

      {/* Import */}
      <button
        className="px-2 py-1 text-xs rounded border border-border text-muted hover:text-gray-200 hover:bg-surface transition-colors"
        onClick={() => fileInputRef.current?.click()}
      >
        Import JSON
      </button>
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        className="hidden"
        onChange={handleImportFile}
      />

      <div className="w-px h-5 bg-border" />

      {/* Undo / Redo */}
      <button
        className="px-2 py-1 text-xs rounded border border-border text-muted hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        onClick={onUndo}
        disabled={!canUndo}
        title="Undo (Ctrl+Z)"
      >
        Undo
      </button>
      <button
        className="px-2 py-1 text-xs rounded border border-border text-muted hover:text-gray-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        onClick={onRedo}
        disabled={!canRedo}
        title="Redo (Ctrl+Shift+Z)"
      >
        Redo
      </button>

      <div className="w-px h-5 bg-border" />

      {/* Auto-edge */}
      <button
        className="px-2 py-1 text-xs rounded border border-border text-muted hover:text-gray-200 hover:bg-surface transition-colors"
        onClick={onAutoEdges}
        title="Generate edges between nearby nodes"
      >
        Auto-Edge
      </button>

      {/* Grid spacing */}
      <label className="flex items-center gap-1 text-xs text-muted">
        Grid:
        <input
          type="number"
          min={0.5}
          max={10}
          step={0.5}
          value={gridSpacing}
          onChange={(e) => onGridSpacingChange(Math.max(0.5, parseFloat(e.target.value) || 2))}
          className="w-12 bg-surface border border-border rounded px-1 py-0.5 text-xs text-gray-200 text-center focus:outline-none focus:border-accent"
        />
        m
      </label>

      <div className="w-px h-5 bg-border" />

      {/* Validate */}
      <button
        className={`px-2 py-1 text-xs rounded border transition-colors ${
          validationResult === null
            ? 'border-border text-muted hover:text-gray-200 hover:bg-surface'
            : validationResult.valid
              ? 'border-success/50 bg-success/10 text-success'
              : 'border-danger/50 bg-danger/10 text-danger'
        }`}
        onClick={handleValidate}
        title="Validate warehouse layout"
      >
        {validationResult === null ? 'Validate' : validationResult.valid ? 'Valid' : 'Invalid'}
      </button>

      {/* Export */}
      <button
        className="px-2 py-1 text-xs rounded border border-accent/50 text-accent hover:bg-accent/10 transition-colors"
        onClick={handleExportDownload}
        title="Download as JSON file"
      >
        Export JSON
      </button>
      <button
        className="px-2 py-1 text-xs rounded border border-accent/50 text-accent hover:bg-accent/10 transition-colors"
        onClick={handleExportServer}
        title="Save to server configs directory"
      >
        Save to Server
      </button>

      {/* Status messages */}
      {exportStatus && (
        <span className="text-[10px] text-warning ml-1">{exportStatus}</span>
      )}
      {validationResult && !validationResult.valid && (
        <span className="text-[10px] text-danger ml-1">
          {validationResult.errors.join('; ')}
        </span>
      )}
      {validationResult && validationResult.warnings.length > 0 && (
        <span className="text-[10px] text-warning ml-1">
          {validationResult.warnings.join('; ')}
        </span>
      )}
    </div>
  )
}
