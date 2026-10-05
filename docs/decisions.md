### Architecture Decision Records
- **Separate Model Servers**: Instead of having one server with two models, we decided to have two separate servers. This decision simplifies the system and makes it easier to manage and scale.
- **Proxy for Routing**: We decided to use a proxy to route role names to the Ollama servers. This decision allows us to maintain a clean separation between the OpenHands agent server and the Ollama servers, and it also makes it easier to manage the system.
- **Binding Ports**: We decided to bind every port to 127.0.0.1. This decision ensures that the system is tightly coupled and can be easily managed.
- **Role Profiles**: Each role has its own profile, which makes it easier to manage and customize the behavior of each role.

### Handoff
- **Components.md**: Describes the components and their responsibilities.
- **API.md**: Defines the interface contracts for the system.
- **Deployment.md**: Provides the deployment topology and constraints.
- **Decisions.md**: Records the architecture decisions made.
- **Handoff.md**: A summary of the produced documentation.

The Tech Lead should read the documentation in the following order: Components.md, API.md, Deployment.md, Decisions.md, and Handoff.md.