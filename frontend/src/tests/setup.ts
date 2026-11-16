import '@testing-library/jest-dom/vitest';
import { afterAll } from 'vitest';

// bits-ui resets body scroll on a 24 ms timer after a dialog unmounts; let it fire before jsdom is torn down
afterAll(() => new Promise((resolve) => setTimeout(resolve, 50)));
