import { useScenarioComparison } from '../hooks/useScenarioApi'
import { ScenarioBarChart } from './ScenarioBarChart'
import type { ScenarioComparisonEntry, ScenarioDelta, ScenarioRanking } from '../types'
import type { WesKpi } from '../types'

const API_BASE = window.location.origin

const CHART_COLORS = ['#89dceb', '#fab387', '#cba6f7', '#a6e3a1', '#f9e2af']

/** Safe accessor for WesKpi fields by string key */
function getKpiValue(kpi: WesKpi, key: string): number {
  switch (key) {
    case 'orders_per_hour': return kpi.orders_per_hour
    case 'throughput_items_per_hour': return kpi.throughput_items_per_hour
    case 'pick_accuracy_pct': return kpi.pick_accuracy_pct
    case 'avg_order_cycle_time_s': return kpi.avg_order_cycle_time_s
    default: return 0
  }
}

const KPI_METRICS: { key: string; label: string; unit: string; higherIsBetter: boolean }[] = [
  { key: 'orders_per_hour', label: 'Orders / Hour', unit: '/hr', higherIsBetter: true },
  { key: 'throughput_items_per_hour', label: 'Throughput', unit: '/hr', higherIsBetter: true },
  { key: 'pick_accuracy_pct', label: 'Pick Accuracy', unit: '%', higherIsBetter: true },
  { key: 'avg_order_cycle_time_s', label: 'Avg Cycle Time', unit: 's', higherIsBetter: false },
]

interface ScenarioComparisonDashboardProps {
  scenarioIds: string[]
  onClose: () => void
}

function DeltaArrow({ value, higherIsBetter }: { value: number; higherIsBetter: boolean }) {
  if (value === 0) return <span className="text-muted">--</span>
  const isPositive = value > 0
  const isBetter = higherIsBetter ? isPositive : !isPositive
  return (
    <span className={isBetter ? 'text-success' : 'text-danger'}>
      {isPositive ? '\u25B2' : '\u25BC'} {Math.abs(value).toFixed(1)}
    </span>
  )
}

function RankingBadge({ ranking }: { ranking: ScenarioRanking }) {
  return (
    <div className="flex items-center gap-2 px-2 py-1 bg-surface rounded text-[10px]">
      <span className="text-yellow-400">#{ranking.rank}</span>
      <span className="text-gray-300 font-medium w-32 truncate">{ranking.name}</span>
      <span className="text-muted">Throughput:</span>
      <span className="text-gray-400 font-mono">{ranking.throughput_items_per_hour.toFixed(1)}/hr</span>
      <span className="text-muted ml-2">Cycle:</span>
      <span className="ml-auto text-gray-400 font-mono">{ranking.avg_order_cycle_time_s.toFixed(1)}s</span>
    </div>
  )
}

export function ScenarioComparisonDashboard({ scenarioIds, onClose }: ScenarioComparisonDashboardProps) {
  const { data: comparison, loading, error } = useScenarioComparison(scenarioIds)

  const handleExport = (format: 'csv' | 'pdf') => {
    const url = `${API_BASE}/api/scenarios/compare?ids=${scenarioIds.join(',')}&format=${format}`
    window.open(url, '_blank')
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-surface text-gray-200 flex items-center justify-center">
        <span className="text-muted text-sm">Loading comparison...</span>
      </div>
    )
  }

  if (error || !comparison) {
    return (
      <div className="min-h-screen bg-surface text-gray-200 flex flex-col items-center justify-center gap-3">
        <span className="text-danger text-sm">{error ?? 'No comparison data'}</span>
        <button
          onClick={onClose}
          className="px-3 py-1 rounded border border-border text-muted hover:text-gray-200 text-xs"
        >
          Back to Dashboard
        </button>
      </div>
    )
  }

  const { scenarios, deltas, rankings } = comparison

  return (
    <div className="min-h-screen bg-surface text-gray-200 flex flex-col">
      {/* Header */}
      <header className="bg-panel border-b border-border px-4 py-2 flex items-center gap-4">
        <button
          onClick={onClose}
          className="text-xs px-3 py-1 rounded border border-border text-muted hover:text-gray-200"
        >
          {'\u2190'} Dashboard
        </button>
        <h1 className="text-lg font-bold text-gray-100 tracking-tight">
          Scenario Comparison
        </h1>
        <span className="text-[10px] text-muted">{scenarios.length} scenarios</span>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => handleExport('csv')}
            className="text-[10px] px-2 py-1 rounded border border-border text-muted hover:text-gray-200"
          >
            Export CSV
          </button>
          <button
            onClick={() => handleExport('pdf')}
            className="text-[10px] px-2 py-1 rounded border border-border text-muted hover:text-gray-200"
          >
            Export PDF
          </button>
        </div>
      </header>

      <main className="flex-1 p-4 overflow-auto space-y-4">
        {/* Config summary table */}
        <div className="bg-panel border border-border rounded-lg p-3">
          <h2 className="text-sm font-semibold text-accent mb-2">Configuration Summary</h2>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px]">
              <thead>
                <tr className="text-muted border-b border-border">
                  <th className="text-left py-1 pr-4">Scenario</th>
                  <th className="text-right py-1 px-2">Fleet</th>
                  <th className="text-left py-1 px-2">Strategy</th>
                  <th className="text-left py-1 px-2">Warehouse</th>
                  <th className="text-right py-1 px-2">Orders</th>
                  <th className="text-right py-1 pl-2">Duration</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((s: ScenarioComparisonEntry, i: number) => (
                  <tr key={s.scenario_id} className="border-b border-border/50">
                    <td className="py-1.5 pr-4">
                      <span className="flex items-center gap-1.5">
                        <span
                          className="inline-block w-2 h-2 rounded-full flex-shrink-0"
                          style={{ backgroundColor: CHART_COLORS[i % CHART_COLORS.length] }}
                        />
                        <span className="text-gray-300 font-medium">{s.name}</span>
                      </span>
                    </td>
                    <td className="text-right py-1.5 px-2 text-gray-400 font-mono">{s.config.fleet_size}</td>
                    <td className="py-1.5 px-2 text-gray-400">{s.config.allocation_strategy}</td>
                    <td className="py-1.5 px-2 text-gray-400">{s.config.warehouse_config}</td>
                    <td className="text-right py-1.5 px-2 text-gray-400 font-mono">{s.config.order_count}</td>
                    <td className="text-right py-1.5 pl-2 text-gray-400 font-mono">{s.config.duration_s}s</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* KPI bar charts */}
        <div className="grid grid-cols-2 gap-3">
          {KPI_METRICS.map((metric) => (
            <div key={metric.key} className="bg-panel border border-border rounded-lg p-3">
              <ScenarioBarChart
                label={metric.label}
                unit={metric.unit}
                values={scenarios
                  .filter((s: ScenarioComparisonEntry) => s.kpis !== null)
                  .map((s: ScenarioComparisonEntry, i: number) => ({
                    name: s.name,
                    value: s.kpis ? getKpiValue(s.kpis, metric.key) : 0,
                    color: CHART_COLORS[i % CHART_COLORS.length],
                  }))}
              />
            </div>
          ))}
        </div>

        {/* Deltas */}
        {deltas.length > 0 && (
          <div className="bg-panel border border-border rounded-lg p-3">
            <h2 className="text-sm font-semibold text-accent mb-2">
              Deltas (vs {scenarios[0]?.name ?? 'baseline'})
            </h2>
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-muted border-b border-border">
                    <th className="text-left py-1 pr-4">Scenario</th>
                    {KPI_METRICS.map((m) => (
                      <th key={m.key} className="text-right py-1 px-2">{m.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {deltas.map((d: ScenarioDelta) => (
                    <tr key={d.scenario_id} className="border-b border-border/50">
                      <td className="py-1.5 pr-4 text-gray-300 font-medium">{d.name}</td>
                      {KPI_METRICS.map((m) => (
                        <td key={m.key} className="text-right py-1.5 px-2">
                          <DeltaArrow
                            value={d.vs_baseline[m.key] ?? 0}
                            higherIsBetter={m.higherIsBetter}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Rankings */}
        {rankings.length > 0 && (
          <div className="bg-panel border border-border rounded-lg p-3">
            <h2 className="text-sm font-semibold text-accent mb-2">Rankings</h2>
            <div className="space-y-1">
              {rankings.map((r: ScenarioRanking) => (
                <RankingBadge key={r.scenario_id} ranking={r} />
              ))}
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
