export default function RootLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-surface)]">
      <div className="flex flex-col items-center gap-4">
        <div className="h-10 w-10 animate-spin rounded-full border-4 border-[var(--color-line)] border-t-[var(--color-accent)]" />
        <p className="text-sm font-medium text-[var(--color-muted)]">Carregando…</p>
      </div>
    </div>
  );
}
