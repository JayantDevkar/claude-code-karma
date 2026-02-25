/**
 * TypeScript declarations for the WebMCP API (Chrome 146+).
 * navigator.modelContext allows websites to expose structured tools to AI agents.
 */

export interface WebMCPTool {
	name: string;
	description: string;
	inputSchema: object;
	handler: (params: Record<string, unknown>) => Promise<unknown>;
}

export interface ModelContextContainer {
	registerTool(tool: WebMCPTool): void;
}

export declare function registerWebMCPTools(): void;
