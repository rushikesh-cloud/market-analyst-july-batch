/** Synthetic session for mocked browser tests; never imported by production. */
const getToken = async () => 'synthetic-browser-test-token'

export function useAuth() {
  return { getToken }
}

export function UserButton() {
  return <button type="button" aria-label="Test account">Test account</button>
}
