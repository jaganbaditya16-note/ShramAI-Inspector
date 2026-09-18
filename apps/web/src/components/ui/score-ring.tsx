"use client";

import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

const RADIUS = 56;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

/** Animated screening-score ring (reduced-motion safe). */
export function ScoreRing({ score, label }: { score: number; label: string }) {
  const reduceMotion = useReducedMotion();
  const [animated, setAnimated] = useState(0);

  useEffect(() => {
    if (reduceMotion) {
      return;
    }
    let frame = 0;
    let handle = 0;
    const totalFrames = 36;
    const step = () => {
      frame += 1;
      const progress = 1 - Math.pow(1 - frame / totalFrames, 3); // ease-out cubic
      setAnimated(Math.round(score * progress));
      if (frame < totalFrames) {
        handle = requestAnimationFrame(step);
      }
    };
    handle = requestAnimationFrame(step);
    return () => cancelAnimationFrame(handle);
  }, [score, reduceMotion]);

  const shown = reduceMotion ? score : animated;
  const clamped = Math.max(0, Math.min(100, shown));
  const color = clamped >= 80 ? "#12b76a" : clamped >= 60 ? "#f79009" : "#d92d20";

  return (
    <div
      className="score-ring"
      role="img"
      aria-label={`Screening score ${clamped} out of 100 — ${label} risk`}
    >
      <svg width="128" height="128" viewBox="0 0 128 128">
        <circle cx="64" cy="64" r={RADIUS} fill="none" stroke="var(--ink-100)" strokeWidth="10" />
        <circle
          cx="64"
          cy="64"
          r={RADIUS}
          fill="none"
          stroke={color}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - clamped / 100)}
        />
      </svg>
      <div className="value">
        <div>
          <strong>{clamped}</strong>
          <small>{label}</small>
        </div>
      </div>
    </div>
  );
}
