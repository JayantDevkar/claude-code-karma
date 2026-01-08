import React from 'react';
import { Box, Text } from 'ink';

interface KeyHint {
  key: string;
  action: string;
}

interface StatusBarProps {
  hints?: KeyHint[];
}

const DEFAULT_HINTS: KeyHint[] = [
  { key: 'q', action: 'Quit' },
  { key: 'r', action: 'Refresh' },
  { key: 't', action: 'Toggle tree' },
  { key: 'h', action: 'Help' },
];

export const StatusBar: React.FC<StatusBarProps> = ({
  hints = DEFAULT_HINTS
}) => {
  return (
    <Box paddingX={1} marginTop={1}>
      {hints.map((hint, i) => (
        <Box key={hint.key} marginRight={2}>
          <Text>[</Text>
          <Text bold color="cyan">{hint.key}</Text>
          <Text>] {hint.action}</Text>
        </Box>
      ))}
    </Box>
  );
};
