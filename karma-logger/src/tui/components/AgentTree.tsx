import React from 'react';
import { Box, Text } from 'ink';
import type { AgentTreeNode } from '../../aggregator.js';

interface AgentTreeProps {
  root: AgentTreeNode | null;
  totalAgents: number;
}

interface TreeNodeProps {
  node: AgentTreeNode;
  prefix?: string;
  isLast?: boolean;
}

const TreeNode: React.FC<TreeNodeProps> = ({ node, prefix = '', isLast = true }) => {
  const connector = isLast ? '└── ' : '├── ';
  const childPrefix = prefix + (isLast ? '    ' : '│   ');

  return (
    <Box flexDirection="column">
      <Box>
        <Text dimColor>{prefix}{connector}</Text>
        <Text color="cyan">{node.type || node.id.slice(0, 8)}</Text>
        <Text dimColor> ({node.model})</Text>
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

export const AgentTree: React.FC<AgentTreeProps> = ({ root, totalAgents }) => {
  return (
    <Box flexDirection="column" paddingX={1}>
      <Text bold dimColor>AGENT TREE ({totalAgents} agents)</Text>
      {root ? (
        <Box flexDirection="column" marginTop={1}>
          <Box>
            <Text color="green">● </Text>
            <Text bold>main</Text>
          </Box>
          {root.children.map((child, i) => (
            <TreeNode
              key={child.id}
              node={child}
              isLast={i === root.children.length - 1}
            />
          ))}
        </Box>
      ) : (
        <Text dimColor>No agents spawned yet</Text>
      )}
    </Box>
  );
};
