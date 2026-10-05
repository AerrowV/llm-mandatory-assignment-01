### Decision 1: Separate Ollama Servers
- **Context**: The system requires two separate Ollama servers to handle different models and ensure isolation.
- **Options**: Combine the two Ollama servers into one server with two models or keep them separate.
- **Decision**: Separate Ollama servers.
- **Consequence**: The system is more isolated and can handle different models without interference.

### Decision 2: Proxy for Routing
- **Context**: The system needs a proxy to route role names to the Ollama servers.
- **Options**: Use the Ollama servers directly or use a proxy.
- **Decision**: Use a proxy.
- **Consequence**: The system can route role names more flexibly and handle different role names without direct access to the Ollama servers.

### Decision 3: Bind Ports to 127.0.0.1
- **Context**: The system requires all ports to be bound to 127.0.0.1 to ensure local communication.
- **Options**: Bind ports to 127.0.0.1 or bind them to all interfaces.
- **Decision**: Bind ports to 127.0.0.1.
- **Consequence**: The system can only communicate locally and is more secure.

### Decision 4: Separate Agent Profiles
- **Context**: Each role has its own profile to define its behavior and API endpoint.
- **Options**: Use a shared profile for all roles or use separate profiles for each role.
- **Decision**: Use separate agent profiles.
- **Consequence**: The system can manage each role independently and ensure each role has its own behavior and API endpoint.