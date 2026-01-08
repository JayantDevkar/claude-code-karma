import React from 'react';
import { Box, Text } from 'ink';

export const App: React.FC = () => {
  return (
    <Box flexDirection="column" width="100%">
      {/* Header */}
      <Box borderStyle="single" paddingX={1}>
        <Text bold>KARMA LOGGER</Text>
        <Box flexGrow={1} />
        <Text dimColor>Session: ---</Text>
      </Box>

      {/* Metrics Row - placeholder */}
      <Box height={5} borderStyle="single" marginTop={1}>
        <Text dimColor>[ Metrics Cards ]</Text>
      </Box>

      {/* Agent Tree - placeholder */}
      <Box height={8} borderStyle="single" marginTop={1}>
        <Text dimColor>[ Agent Tree ]</Text>
      </Box>

      {/* Sparkline - placeholder */}
      <Box height={4} borderStyle="single" marginTop={1}>
        <Text dimColor>[ Token Flow ]</Text>
      </Box>

      {/* Status Bar - placeholder */}
      <Box paddingX={1} marginTop={1}>
        <Text dimColor>[q] Quit  [r] Refresh  [h] Help</Text>
      </Box>
    </Box>
  );
};
