const API_BASE = 'http://localhost:8000/api';

export const api = {
  getHealth: async () => {
    try {
      const res = await fetch('http://localhost:8000/health');
      if (!res.ok) return { status: 'error', model_ready: false };
      return await res.json();
    } catch {
      return { status: 'error', model_ready: false };
    }
  },
  getVideoUrl: (videoId: string) => `${API_BASE}/videos/${videoId}`,
  getAnalytics: async () => {
    const res = await fetch(`${API_BASE}/analytics`);
    if (!res.ok) throw new Error('Failed to fetch analytics');
    return res.json();
  },
  getReports: async () => {
    const res = await fetch(`${API_BASE}/reports`);
    if (!res.ok) throw new Error('Failed to fetch reports');
    return res.json();
  },
  getSequenceValidation: async (experimentId: string) => {
    const res = await fetch(`${API_BASE}/experiments/${experimentId}/sequence`);
    if (!res.ok) throw new Error('Failed to fetch sequence validation');
    return res.json();
  },
  setSequenceConfig: async (experimentId: string, expected_sequence: string[]) => {
    const res = await fetch(`${API_BASE}/experiments/${experimentId}/sequence`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ expected_sequence }),
    });
    if (!res.ok) throw new Error('Failed to set sequence config');
    return res.json();
  },
};
