### Model Servers
- **Ollama Server 1**: Runs on 127.0.0.1:11434 and handles requests for the first model.
- **Ollama Server 2**: Runs on 127.0.0.1:11435 and handles requests for the second model.

### LiteLLM Proxy
- **LiteLLM Proxy**: Runs on 127.0.0.1:4000 and routes role names to the Ollama servers.

### OpenHands Agent Server
- **OpenHands Agent Server**: Runs on 127.0.0.1:8000 and manages six agent roles, each of which interacts with the LiteLLM Proxy.

### Role Prompts
- **Role Prompts**: Define the prompts for each agent role, specifying the expected input and output formats.

### LLM and Agent Profiles
- **LLM Profile**: Defines the configuration for the Ollama servers, including the model names and other settings.
- **Agent Profile**: Defines the configuration for the OpenHands agent server, including the role names and other settings.

### Pipeline Stages
- **Pipeline Stages**: Define the stages of the pipeline, including the OpenHands agent server and the LiteLLM Proxy.