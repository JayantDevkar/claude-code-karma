import React, { useState } from 'react';
import { Box, Text } from 'ink';
import { MetricsCard } from './components/MetricsCard.js';
import { AgentTree } from './components/AgentTree.js';
import { Sparkline } from './components/Sparkline.js';
import { StatusBar } from './components/StatusBar.js';
import { useMetrics } from './hooks/useMetrics.js';
import { useAgentTree } from './hooks/useAgentTree.js';
import { useTokenFlow } from './hooks/useTokenFlow.js';
import { useKeyboard } from './hooks/useKeyboard.js';
import { formatNumber, formatCost } from './utils/format.js';

interface AppProps {
  sessionId?: string;
}

export const App: React.FC<AppProps> = ({ sessionId = '---' }) => {
  const { tokensIn, tokensOut, totalCost } = useMetrics();
  const { root, count } = useAgentTree();
  const tokenFlow = useTokenFlow();
  const [showTree, setShowTree] = useState(true);
  const [showHelp, setShowHelp] = useState(false);

  useKeyboard({
    onToggleTree: () => setShowTree((prev) => !prev),
    onHelp: () => setShowHelp((prev) => !prev),
    onRefresh: () => {
      // Force re-render could be triggered here
    },
  });

  if (showHelp) {
    return (
      <Box flexDirection="column" padding={1}>
        <Text bold>KARMA LOGGER - Help</Text>
        <Box marginTop={1} flexDirection="column">
          <Text><Text bold color="cyan">q</Text>  - Quit the dashboard</Text>
          <Text><Text bold color="cyan">r</Text>  - Refresh metrics</Text>
          <Text><Text bold color="cyan">t</Text>  - Toggle agent tree visibility</Text>
          <Text><Text bold color="cyan">h</Text>  - Show/hide this help</Text>
        </Box>
        <Box marginTop={1}>
          <Text dimColor>Press h to return to dashboard</Text>
        </Box>
      </Box>
    );
  }

  return (
    <Box flexDirection="column" width="100%">
      {/* Header */}
      <Box borderStyle="single" paddingX={1}>
        <Text bold>KARMA LOGGER</Text>
        <Box flexGrow={1} />
        <Text dimColor>Session: {sessionId}</Text>
      </Box>

      {/* Metrics Row */}
      <Box justifyContent="flex-start" gap={2} marginTop={1}>
        <MetricsCard label="Tokens In" value={formatNumber(tokensIn)} color="cyan" />
        <MetricsCard label="Tokens Out" value={formatNumber(tokensOut)} color="green" />
        <MetricsCard label="Total Cost" value={formatCost(totalCost)} color="yellow" />
      </Box>

      {/* Agent Tree */}
      {showTree && (
        <Box
          flexDirection="column"
          borderStyle="single"
          marginTop={1}
          minHeight={8}
        >
          <AgentTree root={root} totalAgents={count} />
        </Box>
      )}

      {/* Sparkline */}
      <Box borderStyle="single" marginTop={1}>
        <Sparkline data={tokenFlow} />
      </Box>

      {/* Status Bar */}
      <StatusBar />
    </Box>
  );
};
