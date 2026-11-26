# AI Ticket Management System

A role-based customer support and ticket management backend built with Django REST Framework and MySQL, with Google Gemini integration for complaint classification and agent-assist reply suggestions.

The system is designed around a complete support workflow: customers submit complaints, support agents review and convert them into tickets, ticket ownership and access are controlled by application roles, SLA deadlines are monitored, escalations are recorded, and customers and agents communicate through ticket conversations.

> **Project status:** Backend authentication, complaint/ticket workflows, AI complaint classification, SLA monitoring and escalation, Knowledge Base/FAQ, ticket messaging, and AI reply suggestions are implemented. React frontend, email notification workflows, analytics/reporting, and deployment remain planned work.

## Table of Contents

- [Features](#features)
- [Technology Stack](#technology-stack)
- [Architecture and Project Structure](#architecture-and-project-structure)
- [Setup](#setup)
- [Environment Variables](#environment-variables)
- [Run the Backend](#run-the-backend)
- [Application Roles and Access Control](#application-roles-and-access-control)
- [Implemented API Endpoints](#implemented-api-endpoints)
- [AI Integration and Reliability](#ai-integration-and-reliability)
- [SLA Monitoring and Escalation](#sla-monitoring-and-escalation)
- [Knowledge Base and FAQs](#knowledge-base-and-faqs)
- [Testing](#testing)
- [Security Notes and Limitations](#security-notes-and-limitations)
- [Roadmap](#roadmap)

## Features

### Authentication and User Management

- Customer registration using email/password.
- Login using username or email and password.
- JWT access and refresh token authentication.
- Refresh-token logout using token blacklisting.
- Authenticated profile retrieval and updates.
- Password reset flow by email.
- Google OAuth ID-token login.
- Authenticated Google account linking.
- Separate application roles for customers, support agents, and application administrators.
- Protected role-management endpoint; users cannot change their own role.

### Complaint Management

- Customers can submit and track their own complaints.
- Complaint records retain the AI-suggested category, priority, sentiment, and summary.
- Agents and administrators can review pending complaints.
- A support agent can convert a complaint into a ticket.
- A complaint can be converted only once.
- If Gemini classification is unavailable, complaint submission continues with documented fallback values rather than failing solely because the AI service is unavailable.

### Ticket Management

- Category-based ticket numbers with year and unique database ID.
- Ticket priorities: LOW, MEDIUM, HIGH, CRITICAL.
- Ticket statuses: OPEN, IN_PROGRESS, RESOLVED, CLOSED.
- Ticket listing, detail retrieval, status/priority updates, and assignment.
- Customers can access only their own tickets.
- Agents can access tickets assigned to them.
- Application administrators can access all tickets.
- Ticket history records creation, assignment, status/priority changes, first response, and escalation events.

### SLA and Escalation Management

- Configurable SLA policies by ticket priority.
- Response and resolution targets and deadlines.
- First-response tracking.
- Response and resolution SLA states: PENDING, MET, BREACHED.
- Response/resolution deadline recalculation when relevant ticket conditions change.
- Resolution SLA handling when a ticket is reopened.
- Multi-level escalation records (Level 1, Level 2, Level 3).
- Escalation reasons include response breach, resolution breach, and manual escalation.
- A Django management command monitors deadlines and creates escalation records.

### Knowledge Base and FAQ

- Knowledge categories.
- Knowledge articles with DRAFT and PUBLISHED states.
- FAQ records with DRAFT and PUBLISHED states.
- Publish workflows for articles and FAQs.
- View-count tracking.
- Customers see published knowledge content; support staff and administrators have broader management access.

### Ticket Messaging

- Customers and authorized support staff can exchange messages within a ticket.
- Messages are stored and returned chronologically.
- Ticket access is checked before a user can read or send messages.
- An assigned agent's first response can update the ticket's response SLA and ticket history when an SLA record exists.

### Gemini AI Reply Suggestions

- Support agents and administrators can request a suggested reply based on ticket details and recent conversation history.
- The latest 30 messages are used as conversation context.
- Prompt instructions prioritize the latest customer concern and discourage invented facts, unsupported claims, and unconfirmed promises.
- Prompt-injection resistance instructions treat ticket and conversation content as untrusted input.
- Empty AI responses are rejected.
- AI service errors are logged and returned as HTTP 503 by the reply-generation endpoint.
- AI drafts are private, transient suggestions: they are not automatically stored as messages or sent to customers. The support agent must review, edit, and send an approved reply using the normal messaging endpoint.

## Technology Stack

| Area | Technology |
| --- | --- |
| Language | Python |
| Backend framework | Django 5.2 |
| API framework | Django REST Framework |
| Database | MySQL |
| Authentication | JSON Web Tokens (Simple JWT) |
| Social login | Google OAuth ID-token verification |
| AI integration | Google Gemini API using the Google Gen AI SDK |
| Configuration | python-decouple / environment variables |
| API verification | Postman |
| Version control | Git and GitHub |

## Architecture and Project Structure

The repository is organized with the Django backend inside `backend/`.

```text
AI-Ticket-Management-System/
├── README.md
└── backend/
    ├── manage.py
    ├── requirements.txt
    ├── .env.example
    ├── accounts/
    │   ├── models.py
    │   ├── permissions.py
    │   ├── serializers.py
    │   ├── urls.py
    │   └── views.py
    └── ticket_Api/
        ├── ai_services/
        │   ├── complaint_classifier.py
        │   └── reply_generator.py
        ├── management/
        │   └── commands/
        │       └── run_sla_monitor.py
        ├── migrations/
        ├── models.py
        ├── serializers.py
        ├── urls.py
        └── views.py
```

## Setup

### Prerequisites

- Python 3.12 or later (the project has been developed and tested with Python 3.14).
- MySQL Server.
- Git.
- A Google OAuth Web Client ID for Google sign-in/linking.
- A Google Gemini API key for AI classification and reply suggestions.

### 1. Clone the repository

```powershell
git clone https://github.com/anjalipatharla/AI-Ticket-Management-System.git
cd AI-Ticket-Management-System/backend
```

### 2. Create and activate a virtual environment

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment Variables

Copy the example configuration file:

```powershell
Copy-Item .env.example .env
```

Create the MySQL database and update the values in `.env`.

| Variable | Purpose |
| --- | --- |
| `SECRET_KEY` | Private Django secret key |
| `DEBUG` | Django debug setting; use `False` in production |
| `ALLOWED_HOSTS` | Comma-separated allowed host names |
| `DB_NAME` | MySQL database name |
| `DB_USER` | MySQL username |
| `DB_PASSWORD` | MySQL password |
| `DB_HOST` | MySQL host |
| `DB_PORT` | MySQL port |
| `GOOGLE_CLIENT_ID` | Google OAuth Web Client ID |
| `GEMINI_API_KEY` | Google Gemini API key |
| `EMAIL_BACKEND` | Django email backend |
| `DEFAULT_FROM_EMAIL` | Sender address for outgoing email |
| `EMAIL_HOST`, `EMAIL_PORT` | SMTP server configuration, if SMTP is used |
| `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP credentials, if SMTP is used |
| `EMAIL_USE_TLS` | Whether SMTP uses TLS |

For local development, the example configuration uses Django's console email backend. Password-reset email content is printed in the terminal running the Django server. Configure a real SMTP provider before using email workflows in a deployed environment.

**Never commit the real `.env` file, API keys, database passwords, or other credentials.**

## Run the Backend

Run these commands from the `backend/` directory after configuring MySQL and `.env`.

Apply database migrations:

```powershell
python manage.py migrate
```

Run Django's system checks:

```powershell
python manage.py check
```

Start the development server:

```powershell
python manage.py runserver
```

The local development server is available at `http://127.0.0.1:8000/`.

## Application Roles and Access Control

The application has three roles:

| Role | Main capabilities |
| --- | --- |
| CUSTOMER | Submit complaints, view own complaints and tickets, and send/receive ticket messages |
| AGENT | Review pending complaints, convert complaints to tickets, manage assigned tickets, communicate with customers, and generate AI reply suggestions |
| ADMIN | Manage application users/roles, access all tickets, and manage support operations |

Public registration creates a CUSTOMER account. Users cannot promote themselves or change their own application role.

### Application Admin versus Django Superuser

A Django superuser and an application ADMIN role are separate concepts. To create the first application administrator:

1. Run `python manage.py createsuperuser`.
2. Sign in to Django admin at `/admin/`.
3. Open Accounts → User profiles.
4. Set the intended user's application role to `ADMIN`.

## Implemented API Endpoints

All paths below are relative to the local backend base URL `http://127.0.0.1:8000`.

### Authentication and Accounts

Base path: `/api/accounts/`

| Method | Endpoint | Access |
| --- | --- | --- |
| POST | `/api/accounts/register/` | Public |
| POST | `/api/accounts/login/` | Public |
| POST | `/api/accounts/token/refresh/` | Public |
| POST | `/api/accounts/logout/` | Authenticated |
| GET, PATCH | `/api/accounts/profile/` | Authenticated; own profile |
| POST | `/api/accounts/forgot-password/` | Public |
| POST | `/api/accounts/reset-password/` | Public; valid reset token required |
| POST | `/api/accounts/google/` | Public; valid Google ID token required |
| POST | `/api/accounts/google/link/` | Authenticated |
| PATCH | `/api/accounts/users/<user_id>/role/` | Application ADMIN |

Protected endpoints use:

```http
Authorization: Bearer <access_token>
```

Google account linking requires the user to authenticate with the existing account first. The supplied Google ID token must be valid for the configured client, have a verified email, and match the signed-in account's email.

### Complaints and Tickets

Base path: `/api/`

| Method | Endpoint | Access |
| --- | --- | --- |
| POST | `/api/complaints/` | CUSTOMER |
| GET | `/api/complaints/my/` | CUSTOMER; own complaints |
| GET | `/api/complaints/pending/` | AGENT or ADMIN |
| POST | `/api/complaints/<complaint_id>/convert/` | AGENT |
| GET | `/api/tickets/` | Authenticated; role-filtered |
| GET | `/api/tickets/<ticket_id>/` | Ticket owner, assigned agent, or ADMIN |
| PATCH | `/api/tickets/<ticket_id>/update/` | Assigned agent or ADMIN |
| POST | `/api/tickets/<ticket_id>/assign/` | Authorized ticket-management role |
| GET | `/api/tickets/<ticket_id>/history/` | Authorized ticket user |

### SLA and Ticket Communication

| Method | Endpoint | Access |
| --- | --- | --- |
| GET, POST | `/api/tickets/<ticket_id>/messages/` | Ticket owner, assigned agent, or ADMIN |
| GET | `/api/tickets/<ticket_id>/first-response/` | Authenticated, subject to view permissions |
| POST | `/api/tickets/<ticket_id>/ai-reply/` | Assigned agent or ADMIN |

### Knowledge Base and FAQs

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET, POST | `/api/knowledge/categories/` | List/create knowledge categories |
| GET, PUT, PATCH, DELETE | `/api/knowledge/categories/<id>/` | Retrieve/manage a category |
| GET, POST | `/api/knowledge/articles/` | List/create knowledge articles |
| GET, PUT, PATCH, DELETE | `/api/knowledge/articles/<id>/` | Retrieve/manage an article |
| POST | `/api/knowledge/articles/<id>/publish/` | Publish an article |
| GET, POST | `/api/faqs/` | List/create FAQs |
| GET, PUT, PATCH, DELETE | `/api/faqs/<id>/` | Retrieve/manage an FAQ |
| POST | `/api/faqs/<id>/publish/` | Publish an FAQ |

Actual permissions depend on the endpoint and HTTP method. The role restrictions above are a high-level guide; the API's permission classes and ticket-ownership checks remain authoritative.

## AI Integration and Reliability

The backend uses the Google Gen AI SDK and the Gemini model `gemini-3.5-flash-lite` for two separate support workflows.

### 1. Complaint Classification

When a customer submits a complaint, the classifier asks Gemini to return structured data:

- Category: BILLING, TECHNICAL, ACCOUNT, or OTHER.
- Suggested priority: LOW, MEDIUM, HIGH, or CRITICAL.
- Sentiment: POSITIVE, NEUTRAL, or NEGATIVE.
- Short complaint summary.

The response is validated against a Pydantic schema before it is used by the complaint workflow.

**Classification fallback:** If the Gemini call fails (including a missing API key or an API/response error), the exception is logged and complaint creation continues with:

| Field | Fallback |
| --- | --- |
| Category | OTHER |
| Priority | MEDIUM |
| Sentiment | NEUTRAL |
| Summary | AI classification is currently unavailable. |

This fallback preserves complaint submission when the external AI service is unavailable. The fallback values are not an AI classification result.

### 2. Agent Reply Suggestions

The reply generator builds a prompt from ticket details and the latest 30 ticket messages. It asks Gemini for a concise customer-facing draft. The endpoint returns the draft to the authorized agent; it does not create a TicketMessage or send an email.

If generation fails, the backend logs the error and the endpoint returns HTTP `503 Service Unavailable` with a generic error response. An empty Gemini output is rejected rather than returned as a usable suggestion.

### Retry Configuration

Both Gemini client configurations use the Google Gen AI SDK retry options:

- Maximum attempts: `3`.
- Initial delay: `1` second.
- Maximum delay: `4` seconds.
- Exponential base: `2`.
- Jitter: `0.5`.
- Configured retryable HTTP status codes: `429`, `500`, `502`, `503`, and `504`.

These settings configure retries for the listed transient HTTP errors. They do not guarantee that every failure will be retried or that the external service will eventually recover.

### AI Safety and Human Review

The reply prompt instructs the model to treat ticket and conversation text as untrusted input, prioritize the latest customer concern, avoid disclosing confidential information, and avoid unsupported claims or promises. These are risk-reduction instructions, not a complete security boundary.

A support agent must review the generated text before sending it. Do not treat an AI-generated draft as proof that an investigation, account change, refund, or resolution has occurred.

## SLA Monitoring and Escalation

SLA policies define response and resolution targets for ticket priorities. Each ticket's SLA record tracks its deadlines and current response/resolution status. The monitoring process checks deadlines and creates escalation records for applicable breaches.

Run the monitoring command manually from `backend/`:

```powershell
python manage.py run_sla_monitor
```

For repeated automatic monitoring on Windows, the command can be scheduled with Windows Task Scheduler. A scheduler must be configured by the operator; the management command does not run continuously by itself.

## Knowledge Base and FAQs

Knowledge articles and FAQs support draft and published states. Publishing is handled through dedicated endpoints. Public-facing authenticated users receive published content, while agents and administrators can access broader content for support operations. Article and FAQ retrieval increments their view counters.

## Testing

Run commands from `backend/` with the virtual environment activated and test database prerequisites configured.

Run account tests:

```powershell
python manage.py test accounts
```

Run ticket API tests:

```powershell
python manage.py test ticket_Api.tests
```

Run all Django tests:

```powershell
python manage.py test
```

The ticket API test suite includes tests for complaint/ticket workflows, role-based access, SLA and escalation behavior, Knowledge Base/FAQ operations, ticket messaging, and AI reply generation. Gemini-dependent behavior is mocked in relevant automated tests so those tests do not require a live Gemini API call.

**Verified test result during the latest documented development check:** `ticket_Api.tests` — 76 tests passed. Test results can change as the code evolves; rerun the commands above to verify the current checkout.

## Security Notes and Limitations

- Keep real secrets in the local `.env` file and never commit it.
- Use a strong private Django `SECRET_KEY`.
- Set `DEBUG=False` and configure production `ALLOWED_HOSTS` before deployment.
- Use HTTPS in production.
- Configure a production email provider before enabling real email delivery.
- Use database credentials with only the permissions the application needs.
- Review authentication, rate limiting, CORS/CSRF, logging, and deployment settings before production use.
- Keep AI-generated replies subject to human review.
- Prompt instructions reduce prompt-injection risk but cannot guarantee complete protection.
- The current repository is a backend project. A React user interface and production deployment are not included yet.

## Roadmap

The following work is not represented as completed:

- React frontend and integration with the backend APIs.
- Email notifications and notification templates/workflows.
- Analytics dashboards and reporting.
- Broader end-to-end testing across a deployed environment.
- Production deployment, hosting configuration, and operational monitoring.

## Repository

[AI-Ticket-Management-System on GitHub](https://github.com/anjalipatharla/AI-Ticket-Management-System)
