import { useEffect, useState } from "react";

/**
 * Registers the palette shortcut once, for the whole app.
 *
 * Cmd+K on a Mac and Ctrl+K elsewhere, plus "/" when the person is not
 * already typing -- the conventions people arrive with from other tools.
 */
export function useCommandPalette(): { open: boolean; setOpen: (open: boolean) => void } {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const typing =
        event.target instanceof HTMLElement &&
        ["INPUT", "TEXTAREA", "SELECT"].includes(event.target.tagName);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
        return;
      }
      if (event.key === "/" && !typing) {
        event.preventDefault();
        setOpen(true);
      }
    };

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return { open, setOpen };
}
