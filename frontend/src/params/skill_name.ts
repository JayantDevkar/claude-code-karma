/**
 * Matcher for the [skill_name] route segment.
 * Only matches skill names without file extensions (e.g. "my-skill" but not "my-skill.md").
 * This ensures paths like /skills/sticky-stack-scroll.md fall through to [...path].
 */
export function match(value: string): boolean {
	return !/\.[a-zA-Z0-9]+$/.test(value);
}
