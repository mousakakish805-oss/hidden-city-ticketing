/**
 * The two drifting colour fields behind the landing page.
 *
 * Purely decorative, so it is hidden from assistive technology and pinned
 * behind everything with no pointer events of its own. The colours come from
 * the accent token, which means it turns from blue to red with the theme
 * without this file knowing either colour.
 */
export function Backdrop() {
  return (
    <div aria-hidden className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      <div
        className="absolute -top-40 -start-32 h-[34rem] w-[34rem] rounded-full
                   animate-drift blur-3xl opacity-[0.18]"
        style={{ background: "radial-gradient(circle, var(--accent), transparent 68%)" }}
      />
      <div
        className="absolute -bottom-56 -end-24 h-[38rem] w-[38rem] rounded-full
                   animate-drift blur-3xl opacity-[0.14]"
        style={{
          background: "radial-gradient(circle, var(--positive), transparent 68%)",
          animationDelay: "-11s",
        }}
      />
    </div>
  );
}
