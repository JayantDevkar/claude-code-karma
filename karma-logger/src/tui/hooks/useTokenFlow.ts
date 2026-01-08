import { useState, useEffect, useRef } from 'react';

const MAX_POINTS = 60;
const POLL_INTERVAL = 1000; // 1Hz

/**
 * Hook for tracking token flow over a 60-second rolling window
 */
export function useTokenFlow(): number[] {
  const [flow, setFlow] = useState<number[]>([]);
  const lastTotal = useRef(0);

  useEffect(() => {
    const interval = setInterval(() => {
      // Simulated - in production, connect to aggregator
      // const current = aggregator.getTotals();
      // const total = current.tokensIn + current.tokensOut;
      // const delta = total - lastTotal.current;
      // lastTotal.current = total;

      // For demo, simulate some activity
      const delta = Math.floor(Math.random() * 100);

      setFlow((prev) => {
        const next = [...prev, delta];
        return next.slice(-MAX_POINTS);
      });
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, []);

  return flow;
}

/**
 * Hook with real aggregator connection
 */
export function useTokenFlowWithAggregator(
  getTotals: () => { tokensIn: number; tokensOut: number }
): number[] {
  const [flow, setFlow] = useState<number[]>([]);
  const lastTotal = useRef(0);

  useEffect(() => {
    const interval = setInterval(() => {
      const current = getTotals();
      const total = current.tokensIn + current.tokensOut;
      const delta = total - lastTotal.current;
      lastTotal.current = total;

      setFlow((prev) => {
        const next = [...prev, delta];
        return next.slice(-MAX_POINTS);
      });
    }, POLL_INTERVAL);

    return () => clearInterval(interval);
  }, [getTotals]);

  return flow;
}
