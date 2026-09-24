import { useEffect, useState } from "react";

/**
 * Whether the tab is currently being looked at.
 *
 * Polling a thread nobody is reading is pure waste: it keeps a free-tier
 * instance awake and spends the viewer's battery to learn nothing. The thread
 * stops polling while this is false and catches up the moment it is true.
 */
export function useVisible(): boolean {
  const [visible, setVisible] = useState(() => typeof document === "undefined" || !document.hidden);

  useEffect(() => {
    const onChange = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);

  return visible;
}
