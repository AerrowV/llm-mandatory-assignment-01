### Model Servers
- **Ollama Server 1**: Runs on 127.0.0.1:11434 and exposes an OpenAI-compatible endpoint for the OpenHands agent to route requests to.
- **Ollama Server 2**: Runs on 127.0.0.1:11435 and exposes an OpenAI-compatible endpoint for the OpenHands agent to route requests to.

### LiteLLM Proxy
- Runs on 127.0.0.1:4000 and routes role names to the Ollama servers based on the OpenHands conversation API.

### OpenHands Agent Server
- Runs on 127.0.0.1:8000 and runs six agent roles against the LiteLLM proxy.

### Role Prompts
- Each role has its own profile and is responsible for a specific task or function.

### LLM and Agent Profiles
- The LLM profiles define the model and API endpoint for each Ollama server.
- The agent profiles define the role and the OpenHands conversation API endpoint for each agent role.

### Pipeline Stages
- The pipeline stages define the sequence of tasks and the OpenHands conversation API calls to be made for each stage.