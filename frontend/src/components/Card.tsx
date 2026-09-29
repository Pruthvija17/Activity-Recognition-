export default function Card({ title, value, alert = false }: { title: string, value: string | React.ReactNode, alert?: boolean }) {
  return (
    <div className={`bg-white rounded-2xl p-6 shadow-sm border ${alert ? 'border-brand-alert/30 bg-red-50/30' : 'border-soft-blue'}`}>
      <h3 className="text-sm font-medium text-brand-secondary mb-2">{title}</h3>
      <div className={`text-3xl font-bold ${alert ? 'text-brand-alert' : 'text-brand-primary'}`}>{value}</div>
    </div>
  );
}
