// Single place that reads the .env values (see .env.example).
export const config = {
  dataSource: import.meta.env.VITE_DATA_SOURCE ?? 'mock',
  apiBaseUrl: import.meta.env.VITE_API_BASE_URL ?? '',
  streamUrl: import.meta.env.VITE_STREAM_URL ?? '',
}
