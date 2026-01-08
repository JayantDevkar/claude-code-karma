import React from 'react';
import { Box, Text } from 'ink';
import type { AgentTreeNode } from '../../aggregator.js';
import { formatCost } from '../utils/format.js';

/**
 * Agent status derived from activity
 */
export type AgentStatus = 'running' | 'complete' | 'error';

/**
 * Status icons for visual indicators
 */
const STATUS_ICONS: Record<AgentStatus, string> = {
  complete: '✓',
  running: '⟳',
  error: '✗',
};

/**
 * Status colors for visual indicators
 */
const STATUS_COLORS: Record<AgentStatus, string> = {
  complete: 'green',
  running: 'yellow',
  error: 'red',
};

/**
 * Threshold (ms) to consider an agent still running
 * Agents with activity within this window are considered running
 */
const RUNNING_THRESHOLD_MS = 5000;

/**
 * Derive agent status from last activity timestamp
 */
function deriveStatus(lastActivity: Date): AgentStatus {
  const now = Date.now();
  const elapsed = now - lastActivity.getTime();
  return elapsed < RUNNING_THRESHOLD_MS ? 'running' : 'complete';
}

interface AgentTreeProps {
  root: AgentTreeNode | null;
  totalAgents: number;
}

interface TreeNodeProps {
  node: AgentTreeNode;
  prefix?: string;
  isLast?: boolean;
}

/**
 * ProgressBar component for running agents
 */
const ProgressBar: React.FC<{ progress: number }> = ({ progress }) => {
  const filled = Math.round(progress / 10);
  const empty = 10 - filled;
  return (
    <Text>
      [<Text color="green">{'█'.repeat(filled)}</Text>
      <Text dimColor>{'░'.repeat(empty)}</Text>] {progress}%
    </Text>
  );
};

/**
 * TreeNode component for recursive tree rendering
 */
const TreeNode: React.FC<TreeNodeProps> = ({ node, prefix = '', isLast = true }) => {
  const connector = isLast ? '└── ' : '├── ';
  const childPrefix = prefix + (isLast ? '    ' : '│   ');

  const status = deriveStatus(node.metrics.lastActivity);
  const icon = STATUS_ICONS[status];
  const color = STATUS_COLORS[status];
  const cost = node.metrics.cost.total;
  const displayName = node.type && node.type !== 'unknown'
    ? node.type
    : node.id.slice(0, 8);

  // Estimate progress for running agents (based on entry count, capped at 90%)
  const progress = status === 'running'
    ? Math.min(90, node.metrics.entryCount * 10)
    : undefined;

  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{prefix}{connector}</Text>
        <Text bold>{displayName}</Text>
        <Text dimColor> ({node.model})</Text>
        <Text>  {formatCost(cost)}</Text>
        {status === 'running' && progress !== undefined ? (
          <Text>  <ProgressBar progress={progress} /></Text>
        ) : (
          <Text color={color}>  {icon}</Text>
        )}
      </Box>
      {node.children.map((child, i) => (
        <TreeNode
          key={child.id}
          node={child}
          prefix={childPrefix}
          isLast={i === node.children.length - 1}
        />
      ))}
    </Box>
  );
};

/**
 * AgentTree component - displays hierarchical view of agents
 */
export const AgentTree: React.FC<AgentTreeProps> = ({ root, totalAgents }) => {
  if (!root) {
    return (
      <Box flexDirection="column" paddingX={1}>
        <Text bold dimColor>AGENT TREE</Text>
        <Text dimColor>No active agents</Text>
      </Box>
    );
  }

  const rootStatus = deriveStatus(root.metrics.lastActivity);
  const rootIcon = STATUS_ICONS[rootStatus];
  const rootColor = STATUS_COLORS[rootStatus];
  const rootCost = root.metrics.cost.total;
  const rootProgress = rootStatus === 'running'
    ? Math.min(90, root.metrics.entryCount * 10)
    : undefined;

  // Use same display name logic as child nodes
  const rootDisplayName = root.type && root.type !== 'unknown'
    ? root.type
    : root.id.slice(0, 8);

  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold dimColor>AGENT TREE</Text>
      <Box flexDirection="column" marginTop={1}>
        {/* Root node */}
        <Box>
          <Text bold>{rootDisplayName}</Text>
          <Text dimColor> ({root.model})</Text>
          <Text>  {formatCost(rootCost)}</Text>
          {rootStatus === 'running' && rootProgress !== undefined ? (
            <Text>  <ProgressBar progress={rootProgress} /></Text>
          ) : (
            <Text color={rootColor}>  {rootIcon}</Text>
          )}
        </Box>
        {/* Child nodes */}
        {root.children.map((child, i) => (
          <TreeNode
            key={child.id}
            node={child}
            isLast={i === root.children.length - 1}
          />
        ))}
      </Box>
      <Text dimColor>└── total agents: {totalAgents}</Text>
    </Box>
  );
};
