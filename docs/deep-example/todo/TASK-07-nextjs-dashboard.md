# TASK-07: Next.js Dashboard

## Objective
Build a Next.js application that displays enriched alerts with business context, supports filtering, and uses the browser Web Notifications API to alert operators of new incidents.

## Components
- Enriched alert feed (polling or SSE from Django GraphQL)
- Alert card components showing business context, severity, recommended actions
- Browser Web Notifications API integration
- Filter controls: by service, severity, business goal, status
- Alert detail view with full enrichment data
- Responsive layout

## Steps
1. Set up Next.js app structure in `next-app/` with TypeScript, Tailwind CSS.
2. Create GraphQL client (using `graphql-request`, `urql`, or Apollo Client) configured to connect to the Django GraphQL endpoint.
3. Implement alert feed data fetching:
   - Option A: Polling — fetch `enrichedAlerts` query every 5 seconds
   - Option B: SSE/WebSocket — subscribe to `onNewAlert` for real-time updates
   - Start with polling, upgrade to subscription if time allows
4. Build `AlertCard` component displaying:
   - Alert title and severity badge (color-coded)
   - Affected service name
   - Business context summary (from enrichment)
   - Recommended actions (collapsible list)
   - Timestamp and status (firing/acknowledged/resolved)
   - "Acknowledge" button triggering `acknowledgeAlert` mutation
5. Build `AlertFeed` component rendering a list of `AlertCard` components, sorted by recency.
6. Implement filter bar with dropdowns/chips for:
   - Service (multi-select)
   - Severity (critical/warning/info)
   - Business goal (multi-select)
   - Status (firing/acknowledged/resolved)
7. Integrate browser Web Notifications API:
   - Request notification permission on first visit
   - Show browser notification when a new alert arrives (title, severity, service)
   - Click notification to focus the dashboard and scroll to the alert
8. Build alert detail page (`/alerts/[id]`) showing full enrichment data, linked SLO definition, business goals, and operational response.
9. Add basic loading states, error boundaries, and empty states.
10. Write component tests with React Testing Library.

## Acceptance Criteria
- [ ] Dashboard loads and displays enriched alerts from the GraphQL API
- [ ] Alert cards show business context, severity, service, and recommended actions
- [ ] Filters narrow the displayed alerts correctly
- [ ] "Acknowledge" button updates alert status via mutation
- [ ] Browser notifications appear for new alerts (with user permission)
- [ ] Alert detail page shows full enrichment data
- [ ] Dashboard is responsive and usable on mobile viewports
- [ ] Component tests pass

## Dependencies
- TASK-01 (project scaffolding — Next.js project must exist)
- TASK-03 (GraphQL API — queries and mutations must be available)

## Estimated Complexity
Large
