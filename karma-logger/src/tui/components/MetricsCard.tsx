import React from 'react';
import { Box, Text } from 'ink';

interface MetricsCardProps {
  label: string;
  value: string;
  color?: string;
}

export const MetricsCard: React.FC<MetricsCardProps> = ({
  label,
  value,
  color = 'white'
}) => {
  return (
    <Box
      flexDirection="column"
      borderStyle="single"
      paddingX={2}
      paddingY={0}
      minWidth={16}
    >
      <Text dimColor>{label}</Text>
      <Text bold color={color}>{value}</Text>
    </Box>
  );
};
