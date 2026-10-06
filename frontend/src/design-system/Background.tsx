import { useEffect, useRef } from "react";

// Cursor-interactive particle field + connecting lines (canvas, no deps).
export function Background() {
  const ref = useRef<HTMLCanvasElement>(null);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    let w = 0, h = 0;
    const mouse = { x: -9999, y: -9999 };
    const dots: { x: number; y: number; vx: number; vy: number; r: number }[] = [];

    function resize() {
      w = canvas!.width = window.innerWidth;
      h = canvas!.height = window.innerHeight;
      const count = Math.min(90, Math.floor((w * h) / 22000));
      dots.length = 0;
      for (let i = 0; i < count; i++) {
        dots.push({ x: Math.random() * w, y: Math.random() * h, vx: (Math.random() - 0.5) * 0.35, vy: (Math.random() - 0.5) * 0.35, r: Math.random() * 1.6 + 0.6 });
      }
    }
    function onMove(e: MouseEvent) { mouse.x = e.clientX; mouse.y = e.clientY; }
    function onLeave() { mouse.x = -9999; mouse.y = -9999; }

    function frame() {
      const light = document.documentElement.getAttribute("data-theme") === "light";
      ctx!.clearRect(0, 0, w, h);
      const dotColor = light ? "rgba(8,145,178," : "rgba(34,211,238,";
      const lineColor = light ? "rgba(13,148,136," : "rgba(45,212,191,";
      for (const d of dots) {
        d.x += d.vx; d.y += d.vy;
        if (d.x < 0 || d.x > w) d.vx *= -1;
        if (d.y < 0 || d.y > h) d.vy *= -1;
        const dx = d.x - mouse.x, dy = d.y - mouse.y;
        const dist = Math.hypot(dx, dy);
        if (dist < 130) { d.x += (dx / dist) * 0.6; d.y += (dy / dist) * 0.6; }
        ctx!.beginPath();
        ctx!.arc(d.x, d.y, d.r, 0, Math.PI * 2);
        ctx!.fillStyle = dotColor + "0.55)";
        ctx!.fill();
      }
      for (let i = 0; i < dots.length; i++) {
        for (let j = i + 1; j < dots.length; j++) {
          const a = dots[i], b = dots[j];
          const dist = Math.hypot(a.x - b.x, a.y - b.y);
          if (dist < 120) {
            ctx!.beginPath();
            ctx!.moveTo(a.x, a.y); ctx!.lineTo(b.x, b.y);
            ctx!.strokeStyle = lineColor + (0.16 * (1 - dist / 120)).toFixed(3) + ")";
            ctx!.lineWidth = 0.7;
            ctx!.stroke();
          }
        }
      }
      raf = requestAnimationFrame(frame);
    }
    resize();
    window.addEventListener("resize", resize);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseleave", onLeave);
    raf = requestAnimationFrame(frame);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", resize);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseleave", onLeave);
    };
  }, []);
  return <canvas id="bg-canvas" ref={ref} aria-hidden="true" />;
}
