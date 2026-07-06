import type { RiskLevel } from './types';

export function formatNumber(value: number | undefined) {
  return Number(value ?? 0).toLocaleString('it-IT');
}

export function formatDate(timestamp: number | undefined) {
  if (!timestamp) return 'Data non disponibile';
  return new Date(timestamp * 1000).toLocaleString('it-IT', {
    dateStyle: 'short',
    timeStyle: 'medium'
  });
}

export function riskLabel(level: RiskLevel | string) {
  return (
    {
      critical: 'Critico',
      high: 'Alto',
      medium: 'Medio',
      low: 'Basso',
      clean: 'Pulito'
    }[level] ?? level
  );
}

export function statusLabel(status: string) {
  return (
    {
      queued: 'In coda',
      running: 'In corso',
      completed: 'Completata',
      failed: 'Fallita',
      clean: 'Pulito',
      findings: 'Finding',
      clone_failed: 'Clone fallito',
      scan_failed: 'Scan fallita'
    }[status] ?? status
  );
}
