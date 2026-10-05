### Deployment Topology
- **Ollama Server 1**: Runs on 127.0.0.1:11434 and handles requests for the first model. It is dependent on the Ollama Server 2 for the second model.
- **Ollama Server 2**: Runs on 127.0.0.1:11435 and handles requests for the second model. It is dependent on the Ollama Server 1 for the first model.
- **LiteLLM Proxy**: Runs on 127.0.0.1:4000 and routes role names to the Ollama servers. It is dependent on both Ollama Servers.
- **OpenHands Agent Server**: Runs on 127.0.0.1:8000 and manages six agent roles, each of which interacts with the LiteLLM Proxy. It is dependent on the LiteLLM Proxy.

### Port Constraints
- **Ollama Server 1**: Exposes port 11434 and uses 127.0.0.1:11434 for communication.
- **Ollama Server 2**: Exposes port 11435 and uses 127.0.0.1:11435 for communication.
- **LiteLLM Proxy**: Exposes port 4000 and uses 127.0.0.1:4000 for communication.
- **OpenHands Agent Server**: Exposes port 8000 and uses 127.0.0.1:8000 for communication.

### Dependencies
- **Ollama Server 1** depends on **Ollama Server 2**.
- **Ollama Server 2** depends on **Ollama Server 1**.
- **LiteLLM Proxy** depends on **Ollama Server 1** and **Ollama Server 2**.
- **OpenHands Agent Server** depends on **LiteLLM Proxy**.

### Constraints
- The **LiteLLM Proxy** must be healthy before the **OpenHands Agent Server** starts.
- No port may be exposed off-host.

### Summary
- The system is built with two separate Ollama servers, each handling requests for a specific model.
- The LiteLLM Proxy routes role names to the Ollama servers.
- The OpenHands agent server manages six agent roles, each interacting with the LiteLLM Proxy.
- Each Ollama server is dependent on the other, and the LiteLLM Proxy is dependent on both Ollama servers.
- The OpenHands agent server is dependent on the LiteLLM Proxy.
- The system is designed to ensure the **LiteLLM Proxy** is healthy before the **OpenHands Agent Server** starts.
- No ports are exposed off-host.
- The system is designed to ensure the **LiteLLM Proxy** is healthy before the **OpenHands Agent Server** starts.
- The system is designed to ensure no ports are exposed off-host.

