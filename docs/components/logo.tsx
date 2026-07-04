export function SteerMark(props: { className?: string }) {
  return (
    <svg
      viewBox="0 0 28 28"
      width="20"
      height="20"
      fill="none"
      aria-hidden="true"
      className={props.className}
    >
      <circle cx="14" cy="14" r="12" stroke="currentColor" strokeWidth="2.5" />
      <circle cx="14" cy="14" r="3" fill="currentColor" />
      <line x1="14" y1="5" x2="14" y2="11" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <line x1="6.2" y1="19.5" x2="11.2" y2="15.8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
      <line x1="21.8" y1="19.5" x2="16.8" y2="15.8" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
