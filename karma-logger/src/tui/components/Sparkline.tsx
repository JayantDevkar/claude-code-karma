import React from 'react';
import { Box, Text } from 'ink';
import asciichart from 'asciichart';

interface SparklineProps {
  data: number[];
  height?: number;
  label?: string;
}

export const Sparkline: React.FC<SparklineProps> = ({
  data,
  height = 3,
  label = 'TOKEN FLOW (last 60s)'
}) => {
  // Ensure we have at least 2 points for chart
  const chartData = data.length < 2
    ? [0, 0]
    : data.slice(-60); // Last 60 seconds

  const chart = asciichart.plot(chartData, {
    height,
    format: (x: number) => x.toFixed(0).padStart(6),
  });

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold dimColor>{label}</Text>
      <Text>{chart}</Text>
    </Box>
  );
};
