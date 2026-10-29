// Small display formatters for table cells.
export const usd = (value) =>
  value == null ? '-' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export const usdCents = (value) =>
  value == null ? '-' : value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 })

export const yesNo = (value) => (value == null ? 'missing' : value ? 'yes' : 'no')

export const lane = (row) => `${row.origin_city} → ${row.destination_city}`
