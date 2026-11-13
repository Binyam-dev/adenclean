# Security review (2026-11-09)

Scope: the server in this repository, its Appwrite use, and the mobile app, as shipped for version 1. The marketplace code is reviewed only for whether it can be reached while switched off.

## Results

| Area | Finding | Status |
| --- | --- | --- |
| Secrets in history | Scanned 57 commits on every local and remote branch plus unreachable objects for key and token patterns, private keys, credential files and database files. No real secret found. Test fixtures and public identifiers (bundle id, Apple team id, Expo project id, Appwrite project id) are not secrets. A pattern scan cannot rule out an oddly named secret. | Clean |
| Secrets in the tree | `APPWRITE_API_KEY` is `sync: false` and `SESSION_SECRET` is generated in `render.yaml`; no `.env` is tracked. `.env.example` has no values. | Clean |
| Python dependencies | `pip-audit -r requirements.txt`: no known vulnerabilities. Packages are version ranges, not hashes. | OK |
| Node dependencies | `npm audit`: 15 moderate, 0 high or critical, all through `glob` and `minimatch` inside Expo's build and lint tools. They do not ship in the app. npm's only fixes are downgrades to old Expo versions. | Accepted; revisit when Expo ships a patch |
| Directory listing | Python's static handler listed any folder under `static/`. Nothing sensitive was there, but one added folder would have been browsable. | **Fixed** (404; test added) |
| Path traversal | `/../main.py` and encoded variants tried. Not served. | Test added |
| Unhandled errors | A bug dropped the connection with no body. | **Fixed**: JSON error, request id, logged, reported |
| Security headers | There were none beyond `nosniff`, `no-referrer`, HSTS. | **Fixed**: CSP (no inline script or style, nothing cross-origin), `X-Frame-Options: DENY`, `Permissions-Policy` |
| Input validation | Every public field goes through `validation.py`: type, trimmed length, control characters, listed values, real dates. Bodies over 16 KB are refused (413) and must be JSON (415). | OK |
| Rate limiting | Per address: 10 submissions, 240 status checks, 10 sign-in attempts per 15 minutes; 120 admin changes. In memory, so a restart resets them. | OK for one instance |
| Private links | 256 random bits, only a SHA-256 hash is stored, one purpose (status and feedback for one request). Wrong and malformed codes get the same 404. Guessing is infeasible and rate limited. Anyone holding a code can act on that request; the privacy policy says so. | OK |
| Admin sign-in | Individual accounts, scrypt (n=2^15), constant-time comparison, a dummy hash for unknown emails, 8-hour signed session, disabling an account takes effect on the next request. | OK |
| Admin cookie | `HttpOnly; Secure; SameSite=Strict; Path=/api/admin`. State-changing calls need JSON content type, which a cross-site form cannot send. | OK |
| Admin authorization | Every `/api/admin/*` route checks the session before reading the body. Status changes check the allowed transition and the current status. | OK |
| Enumeration | Sign-in says the same thing for a wrong password and an unknown email, with equal cost. | OK |
| Appwrite permissions | Tables are created with `permissions=[]` and `row_security=False`, so no client can read or write; only the server key can. The server key needs `rows.read` and `rows.write`. `setup_appwrite.py` needs a broader temporary key that should be deleted after use. Admin password hashes are excluded from backups. | OK; owner deletes the setup key |
| Marketplace while off | With `MARKETPLACE_ENABLED` unset, every `/api/v1/*` path answers 404. In the app, those screens cannot be opened and the payment SDK is not in the binary. | OK |
| Logging | JSON lines with method, path (no query), status, time, request id and the visitor's address. No bodies, cookies or codes. The privacy policy says logs may include IP addresses. | OK (tested) |
| Push tokens (app 1.0.1, off unless `PUSH_ENABLED=1`) | Registering needs the private link code (404 before anything else). Up to 3 phones per request; tokens are never returned by an API, never logged, and stripped from backup exports. The message text is fixed and generic. Sending happens on one background thread after the status is saved, with a 5 s timeout, so Expo being slow or down never delays or fails an admin action. Removed after the first notification about a finished or cancelled request, on a dead-token reply, and on turn-off. Anyone with Appwrite console access can read the tokens. | OK (tested; 18 server tests, mutation-checked) |
| CORS | Off in production. The development-only override accepts one `http://localhost:` origin and is never set on Render. | OK |

## Not done

- A third-party penetration test.
- Account lockout after repeated admin failures beyond the per-address limit. Acceptable with a handful of admins and 12-character minimum passwords.
- Python dependency hashes or a lock file.
- Retention: submissions are kept until deleted by hand (stated in the privacy policy).
