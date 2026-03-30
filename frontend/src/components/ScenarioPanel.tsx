import { useState, useCallback } from 'react'
import { useScenarios, useCreateScenario, useRunScenario } from '../hooks/useScenarioApi'
import type { Scenario, ScenarioStatus, AllocationStrategy } from '../types'

const STATUS_BADGE: Record<ScenarioStatus, string> = {
  created: 'bg-gray-700 text-gray-300',
  running: 'bg-yellow-700 text-yellow-200',
  completed: 'bg-green-700 text-green-200',
  failed: 'bg-red-700 text-red-200',
  archived: 'bg-gray-800 text-gray-500',
}

interface ScenarioPanelProps {
  onCompare: (ids: string[]) => void
}

export function ScenarioPanel({ onCompare }: ScenarioPanelProps) {
  const { data: scenarios } = useScenarios()
  const createScenario = useCreateScenario()
  const runScenario = useRunScenario()

  // Form state
  const [formOpen, setFormOpen] = useState(false)
  const [name, setName] = useState('')
  const [fleetSize, setFleetSize] = useState(10)
  const [robotConfig, setRobotConfig] = useState('differential_drive')
  const [strategy, setStrategy] = useState<AllocationStrategy>('fifo')
  const [warehouseConfig, setWarehouseConfig] = useState('simple_grid')
  const [orderCount, setOrderCount] = useState(50)
  const [durationS, setDurationS] = useState(300)

  // Comparison selection
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const toggleSelected = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const handleCreate = useCallback(async () => {
    if (!name.trim()) return
    await createScenario.execute({
      name: name.trim(),
      description: '',
      fleet_size: fleetSize,
      robot_config: robotConfig,
      allocation_strategy: strategy,
      warehouse_config: warehouseConfig,
      order_count: orderCount,
      order_seed: null,
      duration_s: durationS,
    })
    setName('')
    setFormOpen(false)
  }, [name, fleetSize, robotConfig, strategy, warehouseConfig, orderCount, durationS, createScenario])

  const handleRun = useCallback(
    async (scenarioId: string) => {
      await runScenario.execute(scenarioId)
    },
    [runScenario],
  )

  const handleCompare = useCallback(() => {
    onCompare(Array.from(selected))
  }, [selected, onCompare])

  const list = scenarios ?? []

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <h2 className="text-sm font-semibold text-accent">Scenarios</h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface text-muted">
            {list.length}
          </span>
        </div>
        <button
          onClick={() => setFormOpen((o) => !o)}
          className="text-[10px] px-2 py-0.5 rounded bg-surface text-muted border border-border hover:text-gray-200"
        >
          {formOpen ? 'Cancel' : '+ New'}
        </button>
      </div>

      {/* Create form (collapsible) */}
      {formOpen && (
        <div className="bg-surface rounded p-2 mb-2 space-y-1.5 text-[10px]">
          <input
            type="text"
            placeholder="Scenario name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full bg-panel border border-border rounded px-2 py-1 text-gray-200 placeholder-gray-600 text-[10px]"
          />
          <div className="grid grid-cols-2 gap-1.5">
            <label className="flex flex-col gap-0.5">
              <span className="text-muted">Fleet size</span>
              <input
                type="number"
                value={fleetSize}
                min={1}
                max={100}
                onChange={(e) => setFleetSize(Number(e.target.value))}
                className="bg-panel border border-border rounded px-2 py-1 text-gray-200 text-[10px]"
              />
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-muted">Robot Config</span>
              <select
                value={robotConfig}
                onChange={(e) => setRobotConfig(e.target.value)}
                className="bg-panel border border-border rounded px-2 py-1 text-gray-200 text-[10px]"
              >
                <option value="differential_drive">Differential Drive</option>
                <option value="unidirectional">Unidirectional</option>
              </select>
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-muted">Strategy</span>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value as AllocationStrategy)}
                className="bg-panel border border-border rounded px-2 py-1 text-gray-200 text-[10px]"
              >
                <option value="fifo">FIFO</option>
                <option value="nearest">Nearest</option>
                <option value="priority_weighted">Priority</option>
              </select>
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-muted">Warehouse</span>
              <select
                value={warehouseConfig}
                onChange={(e) => setWarehouseConfig(e.target.value)}
                className="bg-panel border border-border rounded px-2 py-1 text-gray-200 text-[10px]"
              >
                <option value="simple_grid">Simple Grid</option>
                <option value="botvalley">BotValley</option>
              </select>
            </label>
            <label className="flex flex-col gap-0.5">
              <span className="text-muted">Orders</span>
              <input
                type="number"
                value={orderCount}
                min={1}
                max={1000}
                onChange={(e) => setOrderCount(Number(e.target.value))}
                className="bg-panel border border-border rounded px-2 py-1 text-gray-200 text-[10px]"
              />
            </label>
            <label className="flex flex-col gap-0.5 col-span-2">
              <span className="text-muted">Duration (s)</span>
              <input
                type="number"
                value={durationS}
                min={30}
                max={3600}
                onChange={(e) => setDurationS(Number(e.target.value))}
                className="bg-panel border border-border rounded px-2 py-1 text-gray-200 text-[10px]"
              />
            </label>
          </div>
          <button
            onClick={handleCreate}
            disabled={!name.trim() || createScenario.loading}
            className="w-full px-2 py-1 rounded bg-accent text-gray-900 text-[10px] font-bold disabled:opacity-40"
          >
            {createScenario.loading ? 'Creating...' : 'Create'}
          </button>
          {createScenario.error && (
            <div className="text-danger text-[10px]">{createScenario.error}</div>
          )}
        </div>
      )}

      {/* Scenario list */}
      {list.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-[10px]">
          No scenarios yet
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1">
          {list.map((s: Scenario) => (
            <div
              key={s.scenario_id}
              className="flex items-center gap-2 px-2 py-1.5 bg-surface rounded text-[10px]"
            >
              <input
                type="checkbox"
                checked={selected.has(s.scenario_id)}
                onChange={() => toggleSelected(s.scenario_id)}
                className="accent-accent w-3 h-3 flex-shrink-0"
              />
              <span className="text-gray-300 font-medium truncate flex-1">{s.name}</span>
              <span
                className={`px-1.5 py-0.5 rounded font-bold ${STATUS_BADGE[s.status]}`}
              >
                {s.status.toUpperCase()}
              </span>
              {(s.status === 'created' || s.status === 'completed') && (
                <button
                  onClick={() => handleRun(s.scenario_id)}
                  disabled={runScenario.loading}
                  className="px-1.5 py-0.5 rounded border border-border text-muted hover:text-gray-200 disabled:opacity-40"
                >
                  Run
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Compare button */}
      <button
        onClick={handleCompare}
        disabled={selected.size < 2}
        className="mt-2 w-full px-2 py-1.5 rounded bg-accent text-gray-900 text-xs font-bold disabled:opacity-30"
      >
        Compare Selected ({selected.size})
      </button>
      {runScenario.error && (
        <div className="text-danger text-[10px] mt-1">{runScenario.error}</div>
      )}
    </div>
  )
}
