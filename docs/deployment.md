## Deployment Topology
- **Ollama Server 1**: Runs on 127.0.0.1:11434 and handles requests for the first model. It is dependent on the Ollama Server 2 for the second model.
- **Ollama Server 2**: Runs on 127.0.0.1:11435 and handles requests for the second model. It is dependent on the Ollama Server 1 for the first model.
- **LiteLLM Proxy**: Runs on 127.0.0.1:4000 and routes role names to the Ollama servers. It is dependent on both Ollama Servers.
- **OpenHands Agent Server**: Runs on 127.0.0.1:8000 and manages six agent roles, each of which interacts with the LiteLLM Proxy. It is dependent on the LiteLLM Proxy.

## Constraints
- The LiteLLM Proxy must be healthy before the OpenHands Agent Server starts.
- No port may be exposed off-host.

### Dependencies
- The Ollama Server 1 depends on the Ollama Server 2 and vice versa.
- The OpenHands Agent Server depends on the LiteLLM Proxy.
- The LiteLLM Proxy depends on both Ollama Servers.

### Exposed Ports
- Ollama Server 1: 127.0.0.1:11434
- Ollama Server 2: 127.0.0.1:11435
- LiteLLM Proxy: 127.0.0.1:4000
- OpenHands Agent Server: 127.0.0.1:8000