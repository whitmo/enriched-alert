# TASK-03: GraphQL API

## Objective
Expose the Meridian Marketplace data through a Strawberry GraphQL API on Django, including queries, mutations, and a subscription for real-time alert delivery.

## Components
- Strawberry GraphQL schema types mirroring Django models
- Query resolvers: `businessGoals`, `sloDefinitions`, `operationalResponses`, `enrichedAlerts`, plus single-item lookups
- Mutation: `acknowledgeAlert(id) -> EnrichedAlert`
- Subscription: `onNewAlert -> EnrichedAlert` (via Django Channels or SSE)
- GraphQL endpoint at `/graphql` with GraphiQL explorer enabled

## Steps
1. Add `strawberry-graphql-django` and `channels` (or `sse-starlette` equivalent) to Django dependencies.
2. Define Strawberry types for each model: `BusinessGoalType`, `SLODefinitionType`, `OperationalResponseType`, `EnrichedAlertType`, `ServiceType`, `TeamType`.
3. Implement query resolvers:
   - `business_goals(service_id: Optional[ID]) -> List[BusinessGoalType]`
   - `slo_definitions(service_id: Optional[ID]) -> List[SLODefinitionType]`
   - `operational_responses(slo_id: Optional[ID]) -> List[OperationalResponseType]`
   - `enriched_alerts(status: Optional[str], service_id: Optional[ID], severity: Optional[str]) -> List[EnrichedAlertType]`
   - Single-item resolvers by ID for each type
4. Implement `acknowledgeAlert` mutation that sets status to "acknowledged" and records `acknowledged_at` timestamp.
5. Implement `onNewAlert` subscription using Django Channels (WebSocket) or an SSE transport. New alerts pushed when `EnrichedAlert` records are created.
6. Wire up the schema to Django URL conf at `/graphql`.
7. Enable GraphiQL explorer in development mode.
8. Write unit tests for each query resolver and the mutation using pytest and Strawberry's test client.

## Acceptance Criteria
- [ ] `/graphql` endpoint serves the Strawberry GraphiQL explorer
- [ ] All four list queries return correct data with optional filtering
- [ ] Single-item lookups return correct data or appropriate errors
- [ ] `acknowledgeAlert` mutation updates status and timestamp
- [ ] `onNewAlert` subscription delivers new alerts in real time
- [ ] All resolvers handle empty results and invalid IDs gracefully
- [ ] Unit tests pass for queries and mutations

## Dependencies
- TASK-01 (project scaffolding)
- TASK-02 (database models must exist)

## Estimated Complexity
Large
