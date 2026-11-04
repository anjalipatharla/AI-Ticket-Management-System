# AI Ticket Management System — Backend

Django REST Framework backend using MySQL.

## Local setup

1. Create and activate a virtual environment.
2. Install dependencies with `pip install -r requirements.txt`.
3. Create `backend/.env` (do not commit it):

```env
SECRET_KEY=replace-with-a-long-random-secret
DEBUG=True
ALLOWED_HOSTS=127.0.0.1,localhost
DB_NAME=TMS
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_HOST=127.0.0.1
DB_PORT=3306
GOOGLE_CLIENT_ID=your-google-oauth-client-id
EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
DEFAULT_FROM_EMAIL=noreply@example.com
```

4. Create the MySQL database, then run:

```powershell
python manage.py migrate
python manage.py check
python manage.py test accounts
python manage.py runserver
```

## Authentication endpoints

- `POST /api/accounts/register/` — email/password registration; creates a CUSTOMER profile and returns JWT tokens.
- `POST /api/accounts/login/` — username/password JWT login.
- `POST /api/accounts/token/refresh/` — refresh an access token.
- `POST /api/accounts/google/` — Google ID-token login/registration.
- `POST /api/accounts/google/link/` — link Google to the currently authenticated account; the verified Google email must match the signed-in account email.
- `POST /api/accounts/logout/` — blacklist the authenticated user's refresh token.
- `GET/PATCH /api/accounts/profile/` — current user's profile; the role is read-only here.
- `POST /api/accounts/forgot-password/` — request a reset email.
- `POST /api/accounts/reset-password/` — submit UID, token and new password.
- `PATCH /api/accounts/users/<user_id>/role/` — application-admin role assignment.

## Application authorization

Role permission classes are in `accounts/permissions.py`:

- `IsCustomer`
- `IsSupportAgent`
- `IsManager`
- `IsApplicationAdmin`
- `IsAgentOrAbove`
- `IsManagerOrAdmin`
- `IsOwnerOrSupportTeam` — object helper for resources exposing `customer_id`.

The current profile API does not allow users to change their own role. Only an application ADMIN may assign CUSTOMER, AGENT or MANAGER using the role endpoint. ADMIN promotion is intentionally restricted to a trusted command:

```powershell
python manage.py promote_application_admin --username existing_username
```

Django superuser/staff flags and application roles are separate concepts. The command is an operator-controlled bootstrap step.

## Email

The default local backend prints outgoing email to the Django terminal. Configure SMTP environment variables for actual delivery. Password-reset tokens are never returned in the HTTP response or explicitly printed by the view.

## Scope and production notes

The ticket app is currently a placeholder. These role and object-permission helpers must be applied to ticket views when those endpoints are implemented. For list endpoints, filter customer-visible querysets by the authenticated customer; object permissions alone do not filter list results.

Before production, configure HTTPS, production hosts, real SMTP, rate limiting, monitoring, and deployment-specific security settings. This code has not been run against your local MySQL database from this environment.
