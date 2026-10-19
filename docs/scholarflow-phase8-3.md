# ScholarFlow Phase 8.3 — SSE 流式输出验收记录

- **status**: PASS
- **tested_at (UTC)**: `2026-10-18T06:16:53.454781+00:00`
- **model**: `deepseek-chat`
- **stream path**: `ChatDeepSeek.stream` → `AIMessageChunk` 聚合 → SSE `token`
- **API**: `POST /api/v1/conversations/{id}/turns/stream`
- **direct token_count**: `3`
- **tool scenario tool_starts**: `['search_papers']`
- **tool then later tokens**: `True`

## Live 证据（脱敏）

```json
{
  "tested_at": "2026-10-18T06:16:53.454781+00:00",
  "model": "deepseek-chat",
  "scenarios": [
    {
      "title": "sse-direct",
      "content_type": "text/event-stream; charset=utf-8",
      "event_names": [
        "turn_start",
        "token",
        "token",
        "token",
        "done"
      ],
      "token_count": 3,
      "token_preview": "STREAM OK",
      "tool_starts": [],
      "tool_ends": [],
      "done": {
        "event": "done",
        "turn_id": "turn-04460ccf7a33",
        "conversation_id": "cv-5d701649ba51",
        "ts": "2026-10-18T06:16:57.879314Z",
        "status": "completed",
        "assistant_message_id": "msg-004c901de9e5",
        "related_task_id": null,
        "iterations": 1,
        "latency_ms": 4360.4,
        "error": null
      }
    },
    {
      "title": "sse-papers",
      "content_type": "text/event-stream; charset=utf-8",
      "event_names": [
        "turn_start",
        "tool_start",
        "tool_end",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "token",
        "done"
      ],
      "token_count": 83,
      "token_preview": "**Title:** *On the Interpolation of Contextualized Term-based Ranking with BM25 for Query-by-Example Retrieval* (2022)\n\n- Source: https://arxiv.org/abs/2210.05512v1\n- Evidence ID: `paper-2210.05512v1`",
      "tool_starts": [
        "search_papers"
      ],
      "tool_ends": [
        {
          "tool": "search_papers",
          "status": "succeeded",
          "summary": "{\"ok\": true, \"tool\": \"search_papers\", \"papers\": [{\"evidence_id\": \"paper-2210.05512v1\", \"title\": \"On the Interpolation of Contextualized Term-based Ranking with BM25 for Query-by-Ex"
        }
      ],
      "done": {
        "event": "done",
        "turn_id": "turn-7f02c289ec63",
        "conversation_id": "cv-c40da5a1736c",
        "ts": "2026-10-18T06:17:04.455000Z",
        "status": "completed",
        "assistant_message_id": "msg-097bc519c034",
        "related_task_id": null,
        "iterations": 2,
        "latency_ms": 6554.6,
        "error": null
      }
    }
  ]
}
```

