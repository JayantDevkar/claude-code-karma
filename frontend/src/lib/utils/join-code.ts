/**
 * Parse a join code string into its components.
 * Format: team_name:user_id:device_id
 */
export function parseJoinCode(code: string): {
	team: string;
	user: string;
	device: string;
} | null {
	const trimmed = code.trim();
	if (!trimmed) return null;

	const parts = trimmed.split(':');
	if (parts.length < 3) return null;

	const [team, user, ...deviceParts] = parts;
	const device = deviceParts.join(':');

	if (!team || !user || !device) return null;
	return { team, user, device };
}
