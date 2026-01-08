import { render } from 'ink';
import React from 'react';
import { App } from './App.js';

export function startTUI(): void {
  render(React.createElement(App));
}
