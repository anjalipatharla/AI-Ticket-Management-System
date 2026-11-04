# AI Ticket Management System

Django REST Framework backend for an AI-powered ticket and customer support platform.

## Current backend scope

- Email/password customer registration with JWT issuance
- Username-or-email/password JWT login and token refresh
- Refresh-token logout with blacklist
- Authenticated profile retrieval and update
- Password reset by email
- Google OAuth ID-token login
- Authenticated Google account linking
- Application roles: Customer, Support Agent, Manager, Application Admin
- Role-protected application role management
- Scoped rate limits on public authentication endpoints
- Refresh-token revocation after password reset
- Django superuser kept separate from the Application Admin role

Ticket-management APIs, AI services, and the remaining enterprise modules are planned work; the current ticket app is a placeholder.

## Requirements

- Python 3.12+ (the project has been developed with Python 3.14)
- MySQL Server
- Google OAuth Web Client ID for Google sign-in

Install dependencies from the backend directory:

~~~powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
~~~

## Environment configuration

Copy backend/.env.example to backend/.env and set local values. Never commit .env.

Required database values:

- DB_NAME
- DB_USER
- DB_PASSWORD
- DB_HOST
- DB_PORT

Set SECRET_KEY to a unique, private Django secret. Set GOOGLE_CLIENT_ID to the OAuth Web Client ID used by the Google frontend/client flow.

The default email backend is Django's console backend for local development. It prints the reset email to the Django server terminal. Configure SMTP environment variables for real email delivery.

## Database and server

Create the MySQL database first, then run:

~~~powershell
python manage.py migrate
python manage.py check
python manage.py runserver
~~~

The local API base URL is http://127.0.0.1:8000/api/accounts/.

## Authentication endpoints

| Method | Endpoint | Access |
|---|---|---|
| POST | /api/accounts/register/ | Public |
| POST | /api/accounts/login/ | Public; accepts username or email |
| POST | /api/accounts/token/refresh/ | Public |
| POST | /api/accounts/google/ | Public; requires Google ID token |
| POST | /api/accounts/google/link/ | Authenticated |
| POST | /api/accounts/logout/ | Authenticated |
| GET, PATCH | /api/accounts/profile/ | Authenticated; only own profile |
| POST | /api/accounts/forgot-password/ | Public |
| POST | /api/accounts/reset-password/ | Public; requires valid UID/token |

Protected endpoints use the Authorization header with a Bearer access token.

Email registration returns access and refresh tokens immediately. Google login creates a new CUSTOMER account only when the verified Google email is not already registered.

### Linking Google to an existing account

Automatic email-based account linking is deliberately rejected. The user must first authenticate using the existing account, then submit a Google ID token to POST /api/accounts/google/link/ with the access token.

The Google token must be valid for the configured client, have a verified email, and match the signed-in user's email.

## Application roles

- CUSTOMER
- AGENT
- MANAGER
- ADMIN

Public registration always creates CUSTOMER; clients cannot select their own role. Profile updates cannot change the role.

Role permission classes are in accounts/permissions.py and can be applied to future ticket endpoints. The role-management endpoint is:

PATCH /api/accounts/users/<user_id>/role/

It accepts a JSON body with a role field and requires an Application Admin access token. It prevents removal of the last active Application Admin.

### Bootstrap the first Application Admin

1. Create a Django superuser with python manage.py createsuperuser.
2. Sign in to /admin/.
3. Open Accounts > User profiles.
4. Change the selected user's application role to ADMIN.

A Django superuser is not automatically an Application Admin. The distinction is intentional.

## Tests

Run from backend/:

~~~powershell
python manage.py test accounts
~~~

The tests cover registration, JWT login/refresh/logout, profile role protection, Google login/linking, role management, password reset, and refresh-token revocation.

## Security notes

- Keep .env private; use .env.example only as a template.
- Use HTTPS and a production SMTP provider in deployment.
- Keep Google OAuth client secrets out of source code. This backend's ID-token verification needs the client ID, not the client secret.
- Review allowed hosts, debug mode, email, database permissions, rate limits, and deployment security before production.
