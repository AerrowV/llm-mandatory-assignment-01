### Architecture Decision Records
- **Separate Ollama Servers**: Decided to use two separate Ollama servers instead of one server with two models. This decision was made to ensure each model has its own dedicated server, which can improve performance and isolation.
- **Proxy for Routing**: Decided to use a LiteLLM proxy to route role names to the Ollama servers. This decision was made to decouple the agent server from the Ollama servers, making it easier to manage and scale.
- **Role Profiles**: Decided to give each role its own profile rather than a shared profile. This decision was made to ensure each role has its own configuration, which can improve flexibility and customization.

### Consequences
- **Separate Ollama Servers**: This decision means that each model will have its own dedicated server, which can improve performance and isolation. However, it also means that the system will have two separate servers, which may increase complexity and cost.
- **Proxy for Routing**: This decision means that the agent server will need to communicate with the proxy, which may add complexity and introduce potential points of failure. However, it also means that the agent server can be managed independently of the Ollama servers.
- **Role Profiles**: This decision means that each role will have its own configuration, which can improve flexibility and customization. However, it also means that the system will have more configuration options, which may increase complexity and the risk of configuration errors.

