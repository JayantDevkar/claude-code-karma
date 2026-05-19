/**
 * Canonical URL builder for project routes.
 *
 * A project has two identifiers — `slug` (pretty, user-facing) and
 * `encoded_name` (the canonical filesystem-derived form used as DB PK).
 * URLs prefer the slug for legibility but fall back to encoded_name
 * when slug is missing (e.g. on session objects that predate the slug
 * column or live sessions that haven't been indexed yet).
 *
 * Use this helper instead of inlining the `slug || encoded_name`
 * fallback at call sites. The route param `[project_id]` accepts
 * either form and the API normalizes both via
 * `resolve_project_identifier`, so the choice is purely a URL-cosmetics
 * decision — but it should be consistent across the app.
 */

export interface ProjectIdentifierSource {
	slug?: string | null;
	encoded_name?: string | null;
}

/**
 * Build a `/projects/{id}` URL, optionally with a trailing suffix.
 *
 * @example
 * projectHref({ slug: 'claude-karma-1044' })             // → '/projects/claude-karma-1044'
 * projectHref({ encoded_name: '-Users-me-proj' })        // → '/projects/-Users-me-proj'
 * projectHref({ slug: 's', encoded_name: 'e' }, '/abc')  // → '/projects/s/abc'
 */
export function projectHref(p: ProjectIdentifierSource, suffix = ''): string {
	const id = p.slug || p.encoded_name || '';
	return `/projects/${id}${suffix}`;
}

/**
 * Convenience wrapper for sessions — sessions carry both
 * `project_slug` and `project_encoded_name`. Returns just the project
 * identifier, no session segment.
 */
export interface SessionProjectFields {
	project_slug?: string | null;
	project_encoded_name?: string | null;
}

export function projectHrefFromSession(s: SessionProjectFields, suffix = ''): string {
	return projectHref(
		{ slug: s.project_slug, encoded_name: s.project_encoded_name },
		suffix
	);
}
