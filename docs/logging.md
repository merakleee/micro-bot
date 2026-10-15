# Request logs

The API writes one JSON access-log line for each HTTP request. Each response
also includes its generated request identifier in the `X-Request-ID` header.
The logged `path` excludes query parameters. Request and response bodies,
authorization headers, API keys, and other credentials are not logged.

## Chat example

For this response:

```json
{
  "answer": "The club was founded in 2010.",
  "grounded": true,
  "usage": {
    "llm_calls": 1,
    "prompt_tokens": 124,
    "completion_tokens": 38
  },
  "latency_ms": 87
}
```

The corresponding access-log record is:

```json
{"request_id":"9f2e3c2d1c0c4e1e9d1aa3b740095b13","path":"/api/v1/chat","status":200,"latency_ms":87,"llm_calls":1,"prompt_tokens":124,"completion_tokens":38,"access_level":"public","grounded":true}
```

The call and token counts and `grounded` value in the log match the response.
An answer refused for lack of relevant context records zero calls and tokens
with `grounded: false`. Non-chat requests use zero usage counts and `null` for
chat-only fields. If a provider error happens before usage is returned, call
and token counts are `null` because the exact retry count is unknown.
