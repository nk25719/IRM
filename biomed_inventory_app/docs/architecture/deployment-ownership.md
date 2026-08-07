# Deployment Ownership

Cloud Run/FastAPI is the owner of authenticated application routes, API routes, authorization, sessions, uploads, and database-backed views.

Firebase Hosting is limited to static asset delivery and simple legacy redirects that preserve the same canonical destination as FastAPI. Firebase must not route a business page to different content than Cloud Run.

Canonical After Sales ownership:

- `/aftersales` and `/aftersales/*`: Cloud Run/FastAPI
- `/aftersales/preventivemaintenance`: Preventive Maintenance workspace
- `/aftersales/contracts`: Contracts workspace
- `/aftersales/contracts/dashboard`: not a canonical route; do not add Firebase redirects for it
- `/api/*`: Cloud Run/FastAPI
- `/uploads/*`: Cloud Run/FastAPI authorized file delivery

Branch protection should require the `CI / Python checks` workflow before merging to `main`.
