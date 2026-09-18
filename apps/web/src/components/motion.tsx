"use client";

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";

/** Page-level enter transition. Respects prefers-reduced-motion. */
export function PageFade({ children }: { children: ReactNode }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: reduceMotion ? 0 : 0.24, ease: "easeOut" }}
    >
      {children}
    </motion.div>
  );
}

/** Staggered list reveal for findings/results. */
export function RevealList({ children, delay = 0 }: { children: ReactNode; delay?: number }) {
  const reduceMotion = useReducedMotion();
  return (
    <motion.div
      initial={false}
      animate="show"
      variants={{
        show: { transition: { staggerChildren: reduceMotion ? 0 : 0.05, delayChildren: delay } },
      }}
    >
      {children}
    </motion.div>
  );
}

export function RevealItem({ children }: { children: ReactNode }) {
  const reduceMotion = useReducedMotion();
  if (reduceMotion) return <div>{children}</div>;
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0, y: 8 },
        show: { opacity: 1, y: 0, transition: { duration: 0.22, ease: "easeOut" } },
      }}
      initial="hidden"
      animate="show"
    >
      {children}
    </motion.div>
  );
}
