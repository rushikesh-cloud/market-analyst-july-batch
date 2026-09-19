import { useEffect, useRef } from 'react'

export function useDialog(onClose: () => void, busy: boolean) {
  const ref = useRef<HTMLDialogElement>(null)
  useEffect(() => {
    const focused = document.activeElement as HTMLElement | null
    ref.current?.showModal()
    ref.current?.querySelector<HTMLElement>('[data-initial-focus]')?.focus()
    return () => {
      focused?.focus()
    }
  }, [])
  return {
    ref,
    onCancel: (event: React.SyntheticEvent) => {
      event.preventDefault()
      if (!busy) onClose()
    },
  }
}
