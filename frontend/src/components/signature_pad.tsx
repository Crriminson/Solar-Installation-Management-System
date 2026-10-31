/*
  A box the customer signs in with a finger or a mouse.

  Pointer events rather than mouse or touch events, so a stylus, a
  finger and a trackpad all behave the same without three code paths.

  The canvas is sized in device pixels and scaled down in CSS, otherwise
  the stroke looks soft on a phone. The parent gets the signature as a
  PNG blob through onChange, and null whenever the pad is cleared, so it
  can keep its submit button disabled until something has been drawn.
*/

import { useEffect, useRef, useState } from "react";
import Button from "./Button";
import styles from "./signature_pad.module.css";

const WIDTH = 600;
const HEIGHT = 200;
const STROKE_WIDTH = 2.5;            // CSS pixels
const STROKE_COLOUR = "#121826";

interface Props {
  label: string;
  onChange: (signature: Blob | null) => void;
}

export default function SignaturePad({ label, onChange }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef(false);
  const [hasMark, setHasMark] = useState(false);

  /* Set the backing resolution once, then work in CSS pixels. */
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ratio = window.devicePixelRatio || 1;
    canvas.width = WIDTH * ratio;
    canvas.height = HEIGHT * ratio;

    const context = canvas.getContext("2d");
    if (!context) return;
    context.scale(ratio, ratio);
    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, WIDTH, HEIGHT);
    context.lineWidth = STROKE_WIDTH;
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = STROKE_COLOUR;
  }, []);

  function positionOf(event: React.PointerEvent<HTMLCanvasElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    return {
      x: ((event.clientX - bounds.left) / bounds.width) * WIDTH,
      y: ((event.clientY - bounds.top) / bounds.height) * HEIGHT,
    };
  }

  function startStroke(event: React.PointerEvent<HTMLCanvasElement>) {
    const context = canvasRef.current?.getContext("2d");
    if (!context) return;

    /* Capture the pointer so a stroke that leaves the box still ends. */
    event.currentTarget.setPointerCapture(event.pointerId);
    drawing.current = true;

    const { x, y } = positionOf(event);
    context.beginPath();
    context.moveTo(x, y);
  }

  function extendStroke(event: React.PointerEvent<HTMLCanvasElement>) {
    if (!drawing.current) return;
    const context = canvasRef.current?.getContext("2d");
    if (!context) return;

    const { x, y } = positionOf(event);
    context.lineTo(x, y);
    context.stroke();
  }

  function endStroke() {
    if (!drawing.current) return;
    drawing.current = false;
    setHasMark(true);
    canvasRef.current?.toBlob((blob) => onChange(blob), "image/png");
  }

  function clear() {
    const context = canvasRef.current?.getContext("2d");
    if (!context) return;

    context.fillStyle = "#ffffff";
    context.fillRect(0, 0, WIDTH, HEIGHT);
    setHasMark(false);
    onChange(null);
  }

  return (
    <div className={styles.pad}>
      <span className={styles.label}>{label}</span>
      <canvas
        ref={canvasRef}
        className={styles.canvas}
        style={{ aspectRatio: `${WIDTH} / ${HEIGHT}` }}
        onPointerDown={startStroke}
        onPointerMove={extendStroke}
        onPointerUp={endStroke}
        onPointerCancel={endStroke}
        aria-label={label}
        role="img"
      />
      <div className={styles.footer}>
        <span className={styles.hint}>
          {hasMark ? "Signed" : "Sign above with a finger or the mouse"}
        </span>
        <Button type="button" onClick={clear} disabled={!hasMark}>Clear</Button>
      </div>
    </div>
  );
}
