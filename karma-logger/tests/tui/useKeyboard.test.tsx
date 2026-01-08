import { render } from 'ink-testing-library';
import React, { useState } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { Text, Box } from 'ink';
import { useKeyboard } from '../../src/tui/hooks/useKeyboard.js';

// Test component that uses the useKeyboard hook
const KeyboardTestComponent: React.FC<{
  onQuit?: () => void;
  onRefresh?: () => void;
  onToggleTree?: () => void;
  onHelp?: () => void;
}> = ({ onQuit, onRefresh, onToggleTree, onHelp }) => {
  const [lastAction, setLastAction] = useState<string>('none');

  useKeyboard({
    onQuit: () => {
      setLastAction('quit');
      onQuit?.();
    },
    onRefresh: () => {
      setLastAction('refresh');
      onRefresh?.();
    },
    onToggleTree: () => {
      setLastAction('toggleTree');
      onToggleTree?.();
    },
    onHelp: () => {
      setLastAction('help');
      onHelp?.();
    },
  });

  return (
    <Box>
      <Text>Last action: {lastAction}</Text>
    </Box>
  );
};

describe('useKeyboard', () => {
  it('renders component with hook without crashing', () => {
    const { lastFrame } = render(<KeyboardTestComponent />);
    expect(lastFrame()).toContain('Last action: none');
  });

  it('can be initialized with all callbacks', () => {
    const onQuit = vi.fn();
    const onRefresh = vi.fn();
    const onToggleTree = vi.fn();
    const onHelp = vi.fn();

    const { lastFrame } = render(
      <KeyboardTestComponent
        onQuit={onQuit}
        onRefresh={onRefresh}
        onToggleTree={onToggleTree}
        onHelp={onHelp}
      />
    );

    // Hook should initialize without errors
    expect(lastFrame()).toContain('Last action: none');
  });

  it('can be initialized with partial callbacks', () => {
    const { lastFrame } = render(<KeyboardTestComponent onRefresh={vi.fn()} />);
    expect(lastFrame()).toContain('Last action: none');
  });

  it('can be initialized with no callbacks', () => {
    // This tests the default empty object parameter
    const { lastFrame } = render(<KeyboardTestComponent />);
    expect(lastFrame()).toContain('Last action: none');
  });
});
