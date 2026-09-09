import type { ModelLoadProgress } from '../lib/catalog';

export function ModelLoading({ progress }: { progress: ModelLoadProgress | null }) {
  const preparing = progress?.phase === 'preparing';
  const total = progress?.totalBytes;
  const percent = !preparing && total ? Math.min(100, Math.floor(progress.loadedBytes / total * 100)) : undefined;
  const megabytes = (bytes: number) => `${(bytes / 1_000_000).toFixed(2)} MB`;
  const detail = preparing ? 'Download complete. Preparing the 3D view…'
    : progress?.loadedBytes ? `${megabytes(progress.loadedBytes)}${total ? ` of ${megabytes(total)}` : ''} downloaded`
      : total ? `0.00 MB of ${megabytes(total)} downloaded` : 'Waiting for the download to start…';
  return <div className="loading-card" aria-busy="true">
    <strong role="status">{preparing ? 'Preparing model' : 'Downloading model'}</strong>
    <progress aria-label={preparing ? 'Preparing model' : 'Model download'} max={100} value={percent} />
    {percent !== undefined && <div className="loading-percent">{percent}%</div>}
    <p>{detail}</p>
  </div>;
}
