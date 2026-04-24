/**
 * RV monogram — bold typographic mark, no wordmark.
 *
 * Two custom letterforms (heavy slab) set tight together. On hover the letters
 * nudge apart; an orange accent dot sits in the joint between them and pulses
 * slowly while the backend is reachable.
 */
export function Logo({ online = true }: { online?: boolean }) {
  return (
    <div
      className="group relative inline-flex items-center justify-center select-none cursor-default"
      title="revvec"
      aria-label="revvec"
      style={{ width: 40, height: 32 }}
    >
      {online && (
        <span
          className="absolute inset-0 rounded-full bg-accent/10 animate-pulse-slow pointer-events-none"
          aria-hidden
        />
      )}
      <svg
        width="40"
        height="32"
        viewBox="0 0 40 32"
        fill="none"
        className="relative transition-transform duration-300 ease-out group-hover:scale-[1.06]"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id="rvInk" x1="0" y1="0" x2="0" y2="32" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="#0a0a0a" />
            <stop offset="1" stopColor="#262626" />
          </linearGradient>
        </defs>
        {/* R — shifts slightly left on hover */}
        <g className="transition-transform duration-300 ease-out group-hover:-translate-x-[1px]">
          <path
            d="M2 3 H11 C15.4 3 18 5.4 18 9.2 C18 12.4 16 14.6 13 15.3 L18.6 29 H14.1 L9.1 16 H6 V29 H2 V3 Z M6 6.7 V12.5 H10.4 C12.7 12.5 14 11.4 14 9.5 C14 7.7 12.7 6.7 10.4 6.7 H6 Z"
            fill="url(#rvInk)"
          />
        </g>
        {/* V — shifts slightly right on hover */}
        <g className="transition-transform duration-300 ease-out group-hover:translate-x-[1px]">
          <path
            d="M20.8 3 H25.1 L29.8 23.7 H30 L34.7 3 H38.9 L32.4 29 H27.4 L20.8 3 Z"
            fill="url(#rvInk)"
          />
        </g>
        {/* Accent dot in the notch between R and V */}
        <circle
          cx="19.4"
          cy="28"
          r="2"
          fill={online ? "#c2410c" : "#a3a3a3"}
          className="transition-all duration-300 group-hover:fill-[#ea580c]"
        />
      </svg>
    </div>
  );
}
