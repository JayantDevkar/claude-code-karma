export interface LiveEvent {
	id: string;
	type: 'user_prompt' | 'thinking' | 'tool_call' | 'tool_result' | 'response_text';
	content: string;
	tool_name?: string;
	is_error?: boolean;
}
