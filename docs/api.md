### OpenAI-compatible Endpoints
| Method | Path | Parameters | Response | Errors |
| --- | --- | --- | --- | --- |
| GET | /v1/models | model_id | model_id, model_name, model_description | model_not_found |
| GET | /v1/models/{model_id} | model_id | model_id, model_name, model_description | model_not_found |
| POST | /v1/models | model_id, model_name, model_description | model_id | model_already_exists |
| DELETE | /v1/models/{model_id} | model_id | model_id | model_not_found |

### LiteLLM Endpoints
| Method | Path | Parameters | Response | Errors |
| --- | --- | --- | --- | --- |
| GET | /v1/models | model_id | model_id, model_name, model_description | model_not_found |
| GET | /v1/models/{model_id} | model_id | model_id, model_name, model_description | model_not_found |
| POST | /v1/models | model_id, model_name, model_description | model_id | model_already_exists |
| DELETE | /v1/models/{model_id} | model_id | model_id | model_not_found |

### OpenHands Conversation API
| Method | Path | Parameters | Response | Errors |
| --- | --- | --- | --- | --- |
| POST | /v1/conversations | role_name, model_id, user_input | conversation_id, response | model_not_found, user_input_not_provided |
| GET | /v1/conversations/{conversation_id} | conversation_id | conversation_id, response | conversation_not_found |
| DELETE | /v1/conversations/{conversation_id} | conversation_id | conversation_id | conversation_not_found |

Note: All paths are relative to the OpenAI-compatible endpoint.