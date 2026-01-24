# API Performance Report

**Date:** 2026-01-23
**Server:** http://localhost:8000

---

## Detailed Route Testing

### `/analytics/projects/{name}`

| Project | Sessions | Round 1 | Round 2 | Avg |
|---------|----------|---------|---------|-----|
| claude-karma | 268 | 1.423s | 1.076s | **1.250s** |
| dot-claude-files-parser | 77 | 0.491s | 0.830s | **0.660s** |
| ClaudeDashboard | 20 | 0.113s | 0.117s | **0.115s** |
| ap-data-integration | 47 | 0.065s | 0.106s | **0.086s** |
| jayantdevkar (root) | 5 | 0.017s | 0.014s | **0.016s** |

### `/projects/{name}`

| Project | Sessions | Round 1 | Round 2 | Avg |
|---------|----------|---------|---------|-----|
| claude-karma | 268 | 0.597s | 0.946s | **0.772s** |
| dot-claude-files-parser | 77 | 0.179s | 0.165s | **0.172s** |
| ap-data-integration | 47 | 0.122s | 0.114s | **0.118s** |
| ClaudeDashboard | 20 | 0.076s | 0.072s | **0.074s** |
| jayantdevkar (root) | 5 | 0.051s | 0.044s | **0.048s** |

### `/projects/{name}/sessions`

| Project | Sessions | Time |
|---------|----------|------|
| claude-karma | 268 | 0.001s |
| ClaudeDashboard | 20 | 0.001s |
| ap-data-integration | 47 | 0.001s |
| dot-claude-files-parser | 77 | 0.003s |
| jayantdevkar (root) | 5 | 0.004s |

**Observation:** Consistently fast (~1-4ms) regardless of session count

### `/sessions/{uuid}`

| Session UUID | Time |
|--------------|------|
| 1cff4d74-687c-4c76-be91-3e28ed1d43e5 | 0.029s |
| 57c643c3-f739-43e6-9490-e0b6dcbe8fd9 | 0.036s |
| e99aecbb-28ea-4c72-92a5-386127cbe22f | 0.003s |
| 0ce91684-589f-4688-95c7-a0bfce388737 | 0.004s |
| 1fdaf80a-4050-423e-932f-cb0e80b9e9c7 | 0.003s |
| eaeb1fc3-3ca2-4203-bcd3-e21632a7940b | 0.004s |
| 86dbd38e-cc70-4c6f-825a-e621735117d7 | 0.004s |
| 4427a1ab-28a1-4b99-a6fe-273caf77fbab | 0.004s |

**Observation:** Most sessions respond in 3-4ms, some take 29-36ms

---

## Response Times by Endpoint

### Fast Endpoints (< 100ms)

| Endpoint | Time | Response Size | Observations |
|----------|------|---------------|--------------|
| `GET /agents` | 0.005s | 2 bytes | Returns empty array `[]` |
| `GET /skills` | 0.005s | 2 bytes | Returns empty array `[]` |
| `GET /skills/usage` | 0.002s | - | - |
| `GET /history` | 0.001s | - | - |
| `GET /settings` | 0.002s | - | - |
| `GET /projects/{name}/sessions` | 0.002s | - | - |
| `GET /sessions/{uuid}/tools` | 0.032s | - | - |
| `GET /sessions/{uuid}` | 0.055s | - | Session metadata only |
| `GET /live-sessions` | 0.059s | - | - |
| `GET /sessions/{uuid}/file-activity` | 0.062s | - | - |

### Medium Endpoints (100ms - 1s)

| Endpoint | Time | Response Size | Observations |
|----------|------|---------------|--------------|
| `GET /sessions/{uuid}/subagents` | 0.133s | - | Returns empty for this session |
| `GET /sessions/{uuid}/timeline` | 0.203s | 389 KB | Large response, 410+ events |
| `GET /projects/{encoded_name}` | 0.600s | - | Single project details |
| `GET /projects` | 0.723s | 8 KB | Lists all projects |

### Slow Endpoints (> 1s)

| Endpoint | Time | Response Size | Observations |
|----------|------|---------------|--------------|
| `GET /analytics/projects/{name}` | 1.105s | - | Project-specific analytics |
| `GET /analytics` | 2.020s | 4.7 KB | Global analytics aggregation |
| `GET /agents/usage/Plan/history` | 7.636s | - | Usage history for Plan agent |
| `GET /agents/usage/Plan` | 7.714s | - | Single agent usage stats |
| `GET /agents/usage` | 7.763s | 5.2 KB | All agents usage aggregation |
| `GET /agents/usage/Explore` | 8.002s | - | Single agent usage stats |

---

## Observations

1. **Agent usage endpoints consistently take 7-8 seconds** regardless of whether fetching all agents or a single agent type

2. **Response size does not correlate with response time** - `/agents/usage` returns only 5KB but takes 7.7s, while `/sessions/{uuid}/timeline` returns 389KB but takes only 0.2s

3. **Empty responses are fast** - `/agents` and `/skills` return `[]` in under 5ms

4. **Analytics endpoints are slow** - Both global and project-specific analytics take 1-2+ seconds

5. **Session-specific endpoints are fast** - Timeline, tools, file-activity all respond under 250ms

6. **Project listing is moderately slow** - 0.7s to list all projects

7. **All `/agents/usage/*` endpoints have similar timing** - Suggests the same underlying scan operation runs for each request

---

## Raw Timing Data

```
/agents                              0.005s
/agents/usage                        7.763s
/agents/usage/Explore                8.002s
/agents/usage/Plan                   7.714s
/agents/usage/Plan/history           7.636s
/analytics                           2.020s
/analytics/projects/{name}           1.105s
/history                             0.001s
/live-sessions                       0.059s
/projects                            0.723s
/projects/{name}                     0.600s
/projects/{name}/sessions            0.002s
/sessions/{uuid}                     0.055s
/sessions/{uuid}/file-activity       0.062s
/sessions/{uuid}/subagents           0.133s
/sessions/{uuid}/timeline            0.203s
/sessions/{uuid}/tools               0.032s
/settings                            0.002s
/skills                              0.005s
/skills/usage                        0.002s
```
