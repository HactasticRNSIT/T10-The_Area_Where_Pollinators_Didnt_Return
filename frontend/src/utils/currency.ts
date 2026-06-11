export function formatInr(value: number): string {
  if (!Number.isFinite(value) || value <= 0) return '₹0';
  if (value >= 100000) return `₹${(value / 100000).toFixed(1)}L`;
  if (value >= 1000) return `₹${Math.round(value / 1000)}K`;
  return `₹${Math.round(value)}`;
}

