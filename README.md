# AI Ticket Management System

A Django REST Framework backend for an AI-powered ticket management and customer support platform.

## Current Backend Scope

The backend is built using Django REST Framework and MySQL.

### Implemented Features

- Email/password customer registration and JWT authentication.
- Username-or-email/password login.
- JWT access and refresh token management.
- Refresh-token logout with blacklist.
- Authenticated user profile retrieval and updates.
- Password reset by email.
- Google OAuth ID-token login.
- Authenticated Google account linking.
- Role-based access control for Customer, Support Agent and Application Admin.
- Customer complaint submission and tracking.
- Agent access to pending customer complaints.
- Agent-only complaint-to-ticket conversion.
- AI-powered complaint classification using Gemini.
- Automatic category-based ticket number generation.
- Role-based ticket visibility and assignment.
- SLA policies and deadline monitoring.
- Multi-level ticket escalation.
- Knowledge Base and FAQ management.
- Customer-agent ticket messaging.
- AI-powered reply suggestions for support agents.
- Ticket history and audit-related tracking.

### Planned Features

- Email notifications and advanced notification workflows.
- Analytics and reporting.
- React frontend development.
- Final integration testing and deployment.

## Technology Stack

- **Backend:** Python, Django, Django REST Framework
- **Database:** MySQL
- **Authentication:** JWT, Google OAuth
- **AI Integration:** Google Gemini API
- **API Testing:** Postman
- **Version Control:** Git and GitHub

## Requirements

- Python 3.12+
- MySQL Server
- Google OAuth Web Client ID
- Gemini API key

The project has been developed and tested with Python 3.14.

## Installation

Clone the repository:

```powershell
git clone https://github.com/anjalipatharla/AI-Ticket-Management-System.git
```

Navigate to the backend directory:

```powershell
cd AI-Ticket-Management-System/backend
```

Create and activate a virtual environment:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Environment Configuration

Copy `backend/.env.example` to `backend/.env` and configure your local environment variables.

Required database settings:

- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_HOST`
- `DB_PORT`

Other configuration:

- `SECRET_KEY` — a unique, private Django secret.
- `GOOGLE_CLIENT_ID` — Google OAuth Web Client ID.
- `GEMINI_API_KEY` — Google Gemini API key.

Configure the email settings according to your environment.

The default email backend is Django's console backend for local development. Password-reset emails are printed in the Django server terminal.

**Security:** Never commit `.env` files, API keys, passwords or other credentials to GitHub.

## Database Setup and Server

Create the MySQL database first.

Run migrations:

```powershell
python manage.py migrate
```

Check the Django configuration:

```powershell
python manage.py check
```

Start the development server:

```powershell
python manage.py runserver
```

Local server URL:

```text
http://127.0.0.1:8000/
```

## Authentication Endpoints

Base URL: `/api/accounts/`

| Method     | Endpoint                         | Access                               |
| ---------- | -------------------------------- | ------------------------------------ |
| POST       | `/api/accounts/register/`        | Public                               |
| POST       | `/api/accounts/login/`           | Public                               |
| POST       | `/api/accounts/token/refresh/`   | Public                               |
| POST       | `/api/accounts/google/`          | Public; requires Google ID token     |
| POST       | `/api/accounts/google/link/`     | Authenticated                        |
| POST       | `/api/accounts/logout/`          | Authenticated                        |
| GET, PATCH | `/api/accounts/profile/`         | Authenticated; own profile           |
| POST       | `/api/accounts/forgot-password/` | Public                               |
| POST       | `/api/accounts/reset-password/`  | Public; valid UID and token required |

Protected endpoints use the Authorization header:

```text
Authorization: Bearer <access_token>
```

Email registration returns access and refresh tokens immediately.

Google login creates a new CUSTOMER account only when the verified Google email is not already registered.

### Google Account Linking

Automatic email-based account linking is deliberately rejected.

The user must:

1. Authenticate using the existing account.
2. Submit a Google ID token to `/api/accounts/google/link/`.
3. Provide the access token in the Authorization header.

The Google token must be valid for the configured client, contain a verified email and match the signed-in user's email.

## Application Roles

The application supports three roles:

### CUSTOMER

- Submit complaints.
- Track complaints.
- View their own tickets.
- Communicate with support agents.

### AGENT

- Review pending customer complaints.
- Convert complaints into tickets.
- Manage assigned tickets.
- Communicate with customers.
- Generate AI reply suggestions.

### ADMIN

- Manage users and application roles.
- Access all tickets.
- Monitor ticket operations.

Public registration always creates a CUSTOMER account.

Users cannot change their own application roles.

### Role Management Endpoint

| Method | Endpoint                              | Access     |
| ------ | ------------------------------------- | ---------- |
| PATCH  | `/api/accounts/users/<user_id>/role/` | ADMIN only |

### Django Superuser and Application Admin

A Django superuser is not automatically an Application Admin.

To create the first Application Admin:

1. Create a Django superuser using `python manage.py createsuperuser`.
2. Sign in to `/admin/`.
3. Open Accounts → User profiles.
4. Change the selected user's application role to `ADMIN`.

The distinction between Django superuser permissions and application roles is intentional.

## Complaint and Ticket Management

- Customers can submit multiple complaints.
- Agents can view pending customer complaints.
- Only Agents can convert complaints into tickets.
- Each complaint can be converted into only one ticket.
- Ticket numbers are generated automatically using category, year and a unique database ID.
- Customers can view their own tickets.
- Agents can view their assigned tickets.
- Administrators can view all tickets.

### Complaint and Ticket API Endpoints

| Method | Endpoint                                  | Access                 |
| ------ | ----------------------------------------- | ---------------------- |
| POST   | `/api/complaints/`                        | Customer               |
| GET    | `/api/complaints/my/`                     | Customer               |
| GET    | `/api/complaints/pending/`                | Agent, Admin           |
| POST   | `/api/complaints/<complaint_id>/convert/` | Agent                  |
| GET    | `/api/tickets/`                           | Customer, Agent, Admin |

## SLA and Escalation Management

The system includes:

- SLA policies based on ticket priority.
- Response and resolution deadlines.
- First-response tracking.
- SLA status monitoring.
- Deadline recalculation when ticket priority changes.
- Resolution SLA handling when tickets are reopened.
- Multi-level ticket escalation.
- Ticket history tracking.
- Automated SLA monitoring through a Django management command.

The SLA monitoring command is:

```powershell
python manage.py run_sla_monitor
```

For automated execution, configure a scheduler such as Windows Task Scheduler.

## Knowledge Base and FAQ

The system includes:

- Knowledge Base categories.
- Knowledge articles.
- Article publishing workflow.
- FAQ management.
- Article view-count tracking.

These features provide structured support information for customers and support staff.

## Ticket Messaging and AI Reply Generation

### Ticket Messaging

Customers and authorized support staff can exchange messages within tickets.

- Customers can access only their own tickets.
- Agents can access only tickets assigned to them.
- Administrators can access all tickets.
- Messages are stored and retrieved in chronological order.
- An assigned agent's first response can be recorded against the ticket's SLA.

### Messaging API

| Method | Endpoint                             | Access                                     |
| ------ | ------------------------------------ | ------------------------------------------ |
| GET    | `/api/tickets/<ticket_id>/messages/` | Authorized customer, assigned agent, Admin |
| POST   | `/api/tickets/<ticket_id>/messages/` | Authorized customer, assigned agent, Admin |

### AI Reply Generation

The system integrates Google Gemini to generate suggested customer-support replies.

Workflow:

1. Customer sends a message.
2. Support agent views the ticket conversation.
3. Agent requests an AI-generated reply suggestion.
4. Gemini generates a draft using ticket details and recent conversation history.
5. Agent reviews and edits the suggestion.
6. Agent sends the approved reply through the existing messaging API.

AI reply generation includes:

- Conversation-aware reply generation.
- Retrieval of the latest 30 messages.
- Instructions to prioritize the latest customer concern.
- Instructions to avoid unsupported claims and promises.
- Prompt-injection resistance instructions.
- Empty-response validation.
- Error handling when the Gemini service is unavailable.

### AI Reply API

| Method | Endpoint                             | Access                |
| ------ | ------------------------------------ | --------------------- |
| POST   | `/api/tickets/<ticket_id>/ai-reply/` | Assigned agent, Admin |

**Important:** AI suggestions are private to support staff. They are not automatically saved or sent. Support agents must review and approve suggestions before sending them.

Prompt instructions reduce the risk of malicious input influencing AI responses, but they do not guarantee complete protection against prompt injection.

## Tests

Run test commands from the `backend/` directory.

Run account management tests:

```powershell
python manage.py test accounts
```

Run ticket management tests:

```powershell
python manage.py test ticket_Api.tests
```

Run the complete project test suite:

```powershell
python manage.py test
```

The ticket API tests cover complaint and ticket management, SLA and escalation workflows, Knowledge Base and FAQ functionality, ticket messaging and AI reply generation.

AI service tests use mocked Gemini responses where appropriate to verify application behavior without depending on live API calls.

## Security Notes

- Keep `.env` private.
- Use `.env.example` only as a configuration template.
- Never expose API keys, passwords or private credentials.
- Use HTTPS in production.
- Configure a production SMTP provider.
- Review allowed hosts and disable Django debug mode in production.
- Use appropriate database permissions.
- Review rate limits and authentication settings.
- Require support-agent review before sending AI-generated replies.

## Project Repository

GitHub: https://github.com/anjalipatharla/AI-Ticket-Management-System
