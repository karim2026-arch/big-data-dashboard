import { BarChartView } from '../components/charts'
import DashboardShell from '../components/DashboardShell'
import DataTable from '../components/DataTable'
import Panel from '../components/Panel'

export default function PlatformPage() {
  return (
    <DashboardShell dashboardId="platform">
      {(series) => (
        <div className="grid gap-4 lg:grid-cols-2">
          <Panel title="Pipeline runs per day" subtitle="Orchestrated runs (count). 96 per day = one every 15 min.">
            <BarChartView
              data={series.pipeline_runs}
              xKey="run_date"
              bars={[{ key: 'succeeded', label: 'succeeded (runs)', color: '#34d399' }, { key: 'failed', label: 'failed (runs)', color: '#f87171' }]}
              stacked
            />
          </Panel>
          <Panel title="Snowflake credits per warehouse" subtitle="Credits per day, from the warehouses in snowflake/01_setup.sql">
            <BarChartView
              data={series.credits_trend}
              xKey="usage_date"
              bars={[{ key: 'AIRBYTE_WH' }, { key: 'DBT_WH' }, { key: 'BI_WH' }]}
              stacked
            />
          </Panel>
          <Panel
            className="lg:col-span-2"
            title="Row count reconciliation by layer"
            subtitle="Rows per batch table. S3 vs RAW must match (Airbyte lost nothing); STAGING is lower by the removed duplicates."
          >
            <DataTable
              columns={[
                { key: 'table_name', label: 'table_name' },
                { key: 's3_rows', label: 'S3 (rows)' },
                { key: 'raw_rows', label: 'RAW (rows)' },
                { key: 'gap', label: 'S3 - RAW gap (rows)', format: (_, row) => (row.s3_rows - row.raw_rows).toLocaleString('en-US') },
                { key: 'staging_rows', label: 'STAGING (rows)' },
              ]}
              rows={series.row_counts}
            />
          </Panel>
        </div>
      )}
    </DashboardShell>
  )
}
