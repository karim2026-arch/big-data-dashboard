// Small display formatters (table cells, page header).
export const usd = (value) =>
  value == null ? '-' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export const usdCents = (value) =>
  value == null ? '-' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

export const yesNo = (value) => (value == null ? 'missing' : value ? 'yes' : 'no')

// ISO timestamp -> "29 Oct 2026, 11:54" in the viewer's local time.
export const dateTime = (iso) =>
  new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' })

export const lane =(row) => `${row.origin_city} → ${row.destination_city}`
