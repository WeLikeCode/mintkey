# Requirements Document

## Introduction

Budget Management UI for the Mintkey admin console. Operators currently have no way to view, create, edit, or remove budget constraints on permission grants through the AdminJS-based admin-ui. The API layer (ADR-0029) is already implemented — this feature adds the BFF routes and React components to expose budget management to operators via the existing admin console.

All writes flow through the admin-api per ADR-0019 (BFF pattern). The admin-ui holds no direct DB connection.

## Glossary

- **Admin_UI**: The AdminJS 7.x-based admin console (Node 20, Express, pino). A BFF over admin-api per ADR-0019.
- **Budget_Status_Panel**: A React component that displays current budget consumption (used/ceiling), period info, and threshold markers on the permission grant show page.
- **Budget_Form**: A React component providing inputs for ceiling, period, and alert_thresholds when creating or editing a budget constraint.
- **Budget_API_Client**: The set of BFF route handlers that relay budget operations to admin-api endpoints.
- **Operator**: A human user authenticated via Keycloak who manages agents, services, and permissions through the admin console.
- **Permission_Grant**: A record linking an agent to a service with an action and optional constraints (including budget).
- **BudgetStatus**: The response shape from `GET /budget`: `{ceiling, period, used, remaining, period_start, period_end, alert_thresholds}`.

## Requirements

### Requirement 1: View Budget Status

**User Story:** As an operator, I want to see the current budget status on any permission grant that has a budget constraint, so that I can monitor agent consumption at a glance.

#### Acceptance Criteria

1. WHEN an operator navigates to the permission grant show page, THE Budget_Status_Panel SHALL fetch budget data from `GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget` via the BFF.
2. WHILE the permission grant has a budget constraint, THE Budget_Status_Panel SHALL display a progress bar showing used calls relative to the ceiling.
3. WHILE the permission grant has a budget constraint, THE Budget_Status_Panel SHALL display the current period (e.g. "daily"), period start, and period end in human-readable format.
4. WHILE the permission grant has a budget constraint, THE Budget_Status_Panel SHALL display threshold markers on the progress bar at each configured alert_threshold percentage.
5. WHEN the budget API returns an error or the grant has no budget, THE Budget_Status_Panel SHALL display a "No budget configured" message instead of the progress bar.
6. WHEN the used count equals or exceeds the ceiling, THE Budget_Status_Panel SHALL visually indicate exhaustion (e.g. red color on the progress bar).

### Requirement 2: Create Budget on Permission Grant

**User Story:** As an operator, I want to attach a budget constraint when creating a permission grant, so that I can limit agent call volume from the start.

#### Acceptance Criteria

1. WHEN an operator creates a new permission grant, THE Budget_Form SHALL present optional budget fields: ceiling (integer input, minimum 1), period (dropdown: hourly, daily, weekly, monthly), and alert_thresholds (comma-separated integer inputs, each 1-100).
2. WHEN the operator fills in the ceiling and period fields, THE Admin_UI SHALL include `constraints.budget` in the POST body sent to admin-api.
3. WHEN the operator leaves the budget fields empty, THE Admin_UI SHALL omit the `budget` key from `constraints` entirely.
4. IF the operator enters an invalid ceiling (less than 1 or non-integer), THEN THE Budget_Form SHALL display a client-side validation error before submission.
5. IF the operator enters invalid alert_thresholds (values outside 1-100 or non-integer), THEN THE Budget_Form SHALL display a client-side validation error before submission.

### Requirement 3: Edit Budget Constraint

**User Story:** As an operator, I want to edit the ceiling, period, or alert thresholds of an existing budget, so that I can adjust limits without revoking the grant.

#### Acceptance Criteria

1. WHEN an operator clicks "Edit Budget" on the permission grant show page, THE Budget_Form SHALL pre-populate with the current budget values (ceiling, period, alert_thresholds).
2. WHEN the operator submits the edited budget, THE Admin_UI SHALL send a PATCH to `/v1/tenants/{tid}/agents/{aid}/permissions/{pid}` with `{constraints: {budget: {ceiling, period, alert_thresholds}}}` via `apiWrite()`.
3. WHEN the PATCH succeeds, THE Admin_UI SHALL display a success notice and refresh the Budget_Status_Panel with updated data.
4. IF the PATCH returns an error, THEN THE Admin_UI SHALL display the error message from the API response.

### Requirement 4: Remove Budget Constraint

**User Story:** As an operator, I want to remove a budget constraint from a permission grant, so that the agent reverts to unlimited calls.

#### Acceptance Criteria

1. WHEN an operator clicks "Remove Budget" on the permission grant show page, THE Admin_UI SHALL display a confirmation prompt before proceeding.
2. WHEN the operator confirms removal, THE Admin_UI SHALL send a PATCH to `/v1/tenants/{tid}/agents/{aid}/permissions/{pid}` with `{constraints: {budget: null}}` via `apiWrite()`.
3. WHEN the PATCH succeeds, THE Admin_UI SHALL display a success notice and the Budget_Status_Panel SHALL show "No budget configured".
4. IF the API does not support setting budget to null, THEN THE Admin_UI SHALL display an informational message that budget removal requires an API update.

### Requirement 5: Reset Budget Counter

**User Story:** As an operator, I want to reset a budget counter mid-period, so that an agent can resume operations before the next automatic rollover.

#### Acceptance Criteria

1. WHILE the permission grant has a budget constraint, THE Budget_Status_Panel SHALL display a "Reset Budget" button.
2. WHEN the operator clicks "Reset Budget", THE Admin_UI SHALL display a confirmation prompt before proceeding.
3. WHEN the operator confirms the reset, THE Admin_UI SHALL send a POST to `/v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset` via `apiWrite()`.
4. WHEN the POST succeeds, THE Budget_Status_Panel SHALL refresh and display the updated status with `used = 0`.
5. IF the POST returns an error, THEN THE Admin_UI SHALL display the error message from the API response.

### Requirement 6: BFF Route Handlers

**User Story:** As a developer, I want the admin-ui to have BFF route handlers for budget operations, so that the React components can interact with admin-api without direct browser-to-API calls.

#### Acceptance Criteria

1. THE Budget_API_Client SHALL expose a handler that proxies `GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget` and returns BudgetStatus to the frontend.
2. THE Budget_API_Client SHALL expose a handler that proxies `POST /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset` via `apiWrite()` with session + signed JWT.
3. THE Budget_API_Client SHALL expose a handler that proxies `PATCH /v1/tenants/{tid}/agents/{aid}/permissions/{pid}` for budget edits via `apiWrite()`.
4. WHEN a BFF budget handler receives a request, THE Budget_API_Client SHALL extract tenant_id from the session and agent_id from the permission record.
5. IF the admin-api returns an HTTP error, THEN THE Budget_API_Client SHALL forward the error status and message to the frontend unchanged.

### Requirement 7: Enable Edit Action for Budget

**User Story:** As a developer, I want the permissions resource to allow budget editing without exposing the full edit form for all fields, so that budget management is safe and focused.

#### Acceptance Criteria

1. THE Admin_UI SHALL register a custom "editBudget" action on the permission_grants resource (separate from the disabled generic edit action).
2. WHEN the "editBudget" action is triggered, THE Admin_UI SHALL render the Budget_Form component (not the default AdminJS edit form).
3. THE generic edit action on permission_grants SHALL remain disabled (`isVisible: false`).
