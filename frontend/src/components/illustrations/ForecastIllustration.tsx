export function ForecastIllustration() {
  return (
    <svg
      width="160"
      height="120"
      viewBox="0 0 160 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
    >
      <rect
        x="6"
        y="6"
        width="148"
        height="108"
        rx="10"
        stroke="currentColor"
        strokeWidth="2"
        opacity="0.2"
      />
      <path
        d="M18 80 L42 54 L66 72 L90 40 L114 58"
        stroke="var(--color-primary-500)"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      <circle cx="124" cy="50" r="3" fill="var(--color-accent)" opacity="0.25" />
      <circle cx="136" cy="62" r="3" fill="var(--color-accent)" opacity="0.25" />
      <circle cx="148" cy="48" r="3" fill="var(--color-accent)" opacity="0.25" />
    </svg>
  );
}
