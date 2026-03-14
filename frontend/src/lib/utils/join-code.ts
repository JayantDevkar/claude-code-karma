/**
 * Parse a join code string into its components.
 * Supports two formats:
 *   - user_id:device_id            (team-agnostic, preferred)
 *   - team_name:user_id:device_id  (legacy, team included)
 */
export function parseJoinCode(code: string): {
	team: string | null;
	user: string;
	device: string;
} | null {
	const trimmed = code.trim();
	if (!trimmed) return null;

	const parts = trimmed.split(':');

	if (parts.length >= 3) {
		// Legacy format: team:user:device_id
		const [team, user, ...deviceParts] = parts;
		const device = deviceParts.join(':');
		if (!team || !user || !device) return null;
		return { team, user, device };
	}

	if (parts.length === 2) {
		// New format: user:device_id
		const [user, device] = parts;
		if (!user || !device) return null;
		return { team: null, user, device };
	}

	return null;
}
