import { useState, useCallback, useEffect, useRef, type RefObject } from "react";

interface UseResizablePanelsOptions {
  initialWidths: [number, number, number]; // percentages, must sum to 100
  minWidthsPx: [number, number, number]; // minimum widths in pixels
  containerRef: RefObject<HTMLDivElement | null>;
}

export function useResizablePanels({
  initialWidths,
  minWidthsPx,
  containerRef,
}: UseResizablePanelsOptions) {
  const [widths, setWidths] = useState<[number, number, number]>(initialWidths);
  const dragging = useRef<{ handleIndex: number; startX: number; startWidths: [number, number, number] } | null>(null);

  const handleMouseDown = useCallback(
    (handleIndex: number, e: React.MouseEvent) => {
      e.preventDefault();
      dragging.current = {
        handleIndex,
        startX: e.clientX,
        startWidths: [...widths] as [number, number, number],
      };
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";
    },
    [widths],
  );

  useEffect(() => {
    const onMouseMove = (e: MouseEvent) => {
      if (!dragging.current || !containerRef.current) return;
      const { handleIndex, startX, startWidths } = dragging.current;
      const containerWidth = containerRef.current.getBoundingClientRect().width;
      if (containerWidth === 0) return;

      const deltaPx = e.clientX - startX;
      const deltaPct = (deltaPx / containerWidth) * 100;

      const left = handleIndex; // panel index to the left of handle
      const right = handleIndex + 1; // panel index to the right

      let newLeft = startWidths[left] + deltaPct;
      let newRight = startWidths[right] - deltaPct;

      // Enforce min widths
      const minLeftPct = (minWidthsPx[left] / containerWidth) * 100;
      const minRightPct = (minWidthsPx[right] / containerWidth) * 100;

      if (newLeft < minLeftPct) {
        newLeft = minLeftPct;
        newRight = startWidths[left] + startWidths[right] - minLeftPct;
      }
      if (newRight < minRightPct) {
        newRight = minRightPct;
        newLeft = startWidths[left] + startWidths[right] - minRightPct;
      }

      const next: [number, number, number] = [...startWidths] as [number, number, number];
      next[left] = newLeft;
      next[right] = newRight;
      setWidths(next);
    };

    const onMouseUp = () => {
      if (!dragging.current) return;
      dragging.current = null;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
    return () => {
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup", onMouseUp);
    };
  }, [containerRef, minWidthsPx]);

  return { widths, handleMouseDown };
}

export function DragHandle({
  onMouseDown,
}: {
  onMouseDown: (e: React.MouseEvent) => void;
}) {
  return (
    <div
      onMouseDown={onMouseDown}
      className="hidden lg:flex w-1.5 shrink-0 cursor-col-resize items-center justify-center group hover:bg-primary/20 transition-colors relative z-40"
    >
      <div className="w-px h-8 bg-slate-700 group-hover:bg-primary transition-colors rounded-full" />
    </div>
  );
}
