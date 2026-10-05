### Ollama Server 1
- **Endpoint**: `/v1/chat/completions` and `/v1/models`
- **Parameters**: `model`, `prompt`, `max_tokens`, `temperature`, `top_p`, `n`, `stream`, `logprobs`, `stop`, `presence_penalty`, `frequency_penalty`, `repetition_penalty`, `user` (for authentication)
- **Response Shape**: JSON object with `choices` array containing `message` and `finish_reason`
- **Errors**: `model_not_found`, `invalid_model`, `invalid_request`, `internal_server_error`

### Ollama Server 2
- **Endpoint**: `/v1/chat/completions` and `/v1/models`
- **Parameters**: `model`, `prompt`, `max_tokens`, `temperature`, `top_p`, `n`, `stream`, `logprobs`, `stop`, `presence_penalty`, `frequency_penalty`, `repetition_penalty`, `user` (for authentication)
- **Response Shape**: JSON object with `choices` array containing `message` and `finish_reason`
- **Errors**: `model_not_found`, `invalid_model`, `invalid_request`, `internal_server_error`

### LiteLLM Proxy
- **Endpoint**: `/v1/chat/completions` and `/v1/models`
- **Parameters**: `model`, `prompt`, `max_tokens`, `temperature`, `top_p`, `n`, `stream`, `logprobs`, `stop`, `presence_penalty`, `frequency_penalty`, `repetition_penalty`, `user` (for authentication)
- **Response Shape**: JSON object with `choices` array containing `message` and `finish_reason`
- **Errors**: `model_not_found`, `invalid_model`, `invalid_request`, `internal_server_error`