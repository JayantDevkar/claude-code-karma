import { useInput, useApp } from 'ink';

interface KeyboardActions {
  onQuit?: () => void;
  onRefresh?: () => void;
  onToggleTree?: () => void;
  onHelp?: () => void;
}

/**
 * Hook for handling keyboard input in the TUI
 */
export function useKeyboard(actions: KeyboardActions = {}): void {
  const { exit } = useApp();

  useInput((input, key) => {
    if (input === 'q' || (key.ctrl && input === 'c')) {
      actions.onQuit?.();
      exit();
    }

    if (input === 'r') {
      actions.onRefresh?.();
    }

    if (input === 't') {
      actions.onToggleTree?.();
    }

    if (input === 'h') {
      actions.onHelp?.();
    }
  });
}
