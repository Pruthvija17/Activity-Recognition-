// Categorical palette validated for colour-vision deficiency in this fixed order
// (dataviz validator: adjacent CVD delta-E >= 9.1). Colour follows the activity, never its rank.
// Keep in sync with backend/services/analytics.py.
export const ACTIVITIES = [
  'Standing',
  'Sitting',
  'Walking',
  'Reaching',
  'Picking up an object',
  'Placing an object',
  'Handling experimental equipment',
] as const;

export const UNKNOWN = 'Unknown';

export const ACTIVITY_COLORS: Record<string, string> = {
  Standing: '#2a78d6',
  Sitting: '#eb6834',
  Walking: '#1baf7a',
  Reaching: '#eda100',
  'Picking up an object': '#e87ba4',
  'Placing an object': '#008300',
  'Handling experimental equipment': '#4a3aa7',
  Unknown: '#e34948',
};

export const activityColor = (name: string) => ACTIVITY_COLORS[name] ?? '#94a3b8';
