### Deployment Topology
- **Ollama Server 1**: Runs on 127.0.0.1:11434 and is accessible only via localhost.
- **Ollama Server 2**: Runs on 127.0.0.1:11435 and is accessible only via localhost.
- **LiteLLM Proxy**: Runs on 127.0.0.1:4000 and is accessible only via localhost.
- **OpenHands Agent Server**: Runs on 127.0.0.1:8000 and is accessible only via localhost.

### Published Ports
- **Ollama Server 1**: Port 11434 is published.
- **Ollama Server 2**: Port 11435 is published.
- **LiteLLM Proxy**: Port 4000 is published.
- **OpenHands Agent Server**: Port 8000 is published.

### Loopback Ports
- **Ollama Server 1**: Port 11434 is loopback-only.
- **Ollama Server 2**: Port 11435 is loopback-only.
- **LiteLLM Proxy**: Port 4000 is loopback-only.
- **OpenHands Agent Server**: Port 8000 is loopback-only.

### Dependencies
- **Ollama Server 1** depends on **Ollama Server 2**.
- **Ollama Server 2** depends on **Ollama Server 1**.
- **LiteLLM Proxy** depends on **Ollama Server 1** and **Ollama Server 2**.
- **OpenHands Agent Server** depends on **LiteLLM Proxy**.

### Constraints
- **Ollama Server 1** must be healthy before **OpenHands Agent Server** starts.
- **Ollama Server 2** must be healthy before **OpenHands Agent Server** starts.
- **LiteLLM Proxy** must be healthy before **OpenHands Agent Server** starts.
- No port may be exposed off-host.