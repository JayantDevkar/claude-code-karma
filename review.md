# PR #57 Review Notes

## Already fixed (in this branch)
- **`+page.server.ts:55-68`** — live session fetch moved into `Promise.all` with the other 5 agent fetches so all 6 fire in parallel instead of sequentially.
- **`routers/subagent_sessions.py`** — ruff formatting pass on the new `get_subagent_live_status` function (long ternaries, headers dict).

---

## Remaining polish suggestions

### Medium

**`+page.server.ts:56`** — Comment still says "Step 1" / "Step 2" but there is no step numbering convention elsewhere in the codebase. Consider removing step labels entirely for cleaner code.

**`routers/subagent_sessions.py:402-412`** — When the parent session exists but `agent_id` is not in `state.subagents`, the endpoint returns `200` with `"subagent": null`. The docstring only documents the `404` case. Add a note describing the `null` case so callers know to handle it.

```python
# Add to docstring:
# Returns 200 with subagent=null if the parent session is tracked
# but this agent_id has not been registered yet.
```

### Low

**`services/subagent_types.py:304,337`** — Both the Task input prompt and the agent's initial prompt are truncated to 100 chars before comparison. Two agents with identical first 100 chars of prompt in the same session would get the wrong type assigned. No action needed unless this causes false positives in real usage.

**`services/subagent_types.py:306,309`** — `prompt[:100]` and `description[:100]` are stored in the same `prompt_to_type` dict. A Task whose truncated `description` matches another Task's truncated `prompt` would silently overwrite the type mapping. Low probability but worth a comment noting the risk.

**`routers/subagent_sessions.py:384`** — New `/live-status` endpoint exists but is not called by the frontend. It reads from the parent session's live state directly. Either wire it up in a follow-up or add a `# TODO` comment noting it is reserved for future use.

---

## Not issues

- **Active/idle inconsistency between agent detail page and session subagents tab** — intentional by design. The subagents tab uses the raw `SubagentStatus` type (`running`/`completed`/`error`). The active/idle enhancement is scoped to the agent detail header only. Known limitation, not a bug.
- **`isSubagentCompleted` returns false when `liveStatus` is null** — one extra poll fires then stops on 404. Functionally invisible.
- **100-char truncation edge cases** — only relevant if two agents in the same session share identical prompt prefixes. No action needed.
