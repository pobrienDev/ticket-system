// The same ticket-stub mark as the favicon, in white on the accent square.
function Logo() {
  return (
    <span className="logo" aria-hidden="true">
      <svg viewBox="0 0 32 32" width="22" height="22" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M4 9a2 2 0 0 1 2-2h20a2 2 0 0 1 2 2v3.5a3.5 3.5 0 0 0 0 7V23a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2v-3.5a3.5 3.5 0 0 0 0-7Z"
          fill="#fff"
        />
        <path
          d="M20 9v2m0 4v2m0 4v2"
          stroke="var(--accent-strong)"
          strokeWidth="2"
          strokeLinecap="round"
          strokeDasharray="2 4"
        />
      </svg>
    </span>
  )
}

export default Logo
