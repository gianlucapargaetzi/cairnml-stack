# ClearML with our identity provider: final proposal

Written for: you, as the person who decides and maintains the fork. It assumes no security background; terms are explained in section 1.

---

## 0. Summary

- **ClearML is the only platform.** We fork its four repositories (server, agent, SDK, web app) and change them where they don't fit. No additional service is added.
- **One identity layer:** the identity provider (IdP, Keycloak) identifies people and signs them in. Laptops, agents and jobs are then identified by device keys and short-lived access tokens, which the ClearML server signs. ClearML keeps no passwords, no user access keys and no roles of its own. Its only keys are server secrets: storage, GitHub, database, and the signing key for its access tokens.
- **Sign-in and enrolment:** people sign in through the IdP's browser flow. A laptop or agent signs in once through the IdP, then registers a key pair with the ClearML server, and from then on signs each request with its private key. This is the same mechanism our server uses today. Agent enrolment needs an admin's approval.
- **Revocation at two levels:** disable a user to stop all their access, or revoke one device's key on the ClearML server. A revoked device is refused on its next request. Disabling a user takes effect within about a minute, the same as in our server: the ClearML server refreshes its copy of each user's status from the IdP every 60 seconds.
- **Access tokens:** the ClearML server signs the short-lived access tokens of laptops, agents and jobs, the same way our server does today. Keycloak signs only the sign-in tokens it issues during enrolment and sign-in.
- **Short-lived storage credentials:** the ClearML server asks RustFS for temporary, per-project storage credentials, as our server does today.
- **GitHub:** the ClearML server mints a short-lived GitHub App token per job, scoped to the repository that job needs.
- **Audit:** added to the fork, since the open-source ClearML server has none.
- **Secrets:** the server keeps the same kinds of secrets as our server today (storage, GitHub App key, database password, and the signing key for its access tokens), loaded from files in a read-only mount.
- **Effort:** about 7 to 10 weeks for one experienced developer, plus about 2 weeks for a security review. Per-project permissions come later and are not included.
- **Main risk:** every ClearML upgrade has to be merged by hand. The fork has one owner, who is you.

---

## 1. Terms, in plain language

- **Identity provider (IdP).** The one service that knows who people are and decides what they may do. Here, Keycloak 26.0.
- **Token.** A short string that proves who is asking. A **JWT** is a signed token: the IdP signs it, and any service can check the signature with the IdP's public key. A forged token fails that check.
- **Device flow (RFC 8628).** How a command-line tool signs in: it shows a short code and a web address, the person approves in the browser, and the tool receives its token. Our client already uses it.
- **Job token.** A short-lived token that ClearML issues to one running job, limited to that job and signed by the ClearML server. It ends when the job ends.
- **Device key.** A key pair created on a laptop or agent. The private key never leaves the machine; the public key is registered with the ClearML server. Every request is proven with the private key, so a copied token alone is useless.
- **Assertion.** A short, signed message that proves a device holds its key. Each assertion carries a unique ID, so it can't be replayed.
- **Access token.** The short-lived token sent with each request. It expires within minutes.
- **Secret.** A password or key that must stay private: database password, storage key, GitHub App key.
- **Revocation.** Cancelling a token or a user so it stops working.

---

## 2. Current state of each system

### 2.1 Ours

| Interface | How identity is proven |
|---|---|
| Browser ↔ server | IdP sign-in, then a session cookie |
| Client (laptop CLI) ↔ server | IdP sign-in once, then a signed assertion per token request, checked against the registered public key |
| Agent ↔ server | one-time enrolment token created by an admin |
| Run / job ↔ server | a run token issued by our server, valid for that run |
| Storage | short-lived credentials from RustFS, per project |
| GitHub | a read-only GitHub App, short-lived installation tokens per repository |

Our server holds these secrets: storage keys, the GitHub App key, a signing key for its own tokens, the database password and the IdP sync secret.

### 2.2 ClearML (open source)

| Interface | How identity is proven |
|---|---|
| Browser ↔ server | username and password, or access keys; ClearML issues its own JWT |
| SDK ↔ server | access key and secret key, copied into the terminal |
| Agent ↔ server | access key and secret key of the user who set it up |
| File server | a shared service credential |
| Audit | none in the open-source server |

---

## 3. Side-by-side with the final design

| Topic | Ours | ClearML, final design |
|---|---|---|
| Who is a user | IdP | IdP; ClearML keeps a read-only record for display |
| Passwords and access keys | not used for people | removed |
| Sign-in for people | IdP | IdP only |
| Laptop enrolment | IdP sign-in, then the public key is registered with the server | IdP sign-in, then the public key is registered with the ClearML server |
| Agent enrolment | admin one-time token | IdP device flow, approved by an admin |
| Revocation, per machine | yes, one key | yes, one key per device on the ClearML server |
| Revocation, per user | yes | yes, by disabling the user in the IdP |
| Job identity | run token from our server | per-job token, signed by the ClearML server |
| Storage access | short-lived, per project | short-lived, per project (same pattern) |
| GitHub access | read-only App, installation tokens | GitHub App installation tokens per job |
| Audit | our audit events | added to the fork |
| Per-project membership | yes | not yet (later) |
| Signing key for our tokens | yes | yes, for access tokens of devices, agents and jobs; the IdP signs only sign-in tokens |
| Secrets held by the server | storage, GitHub, database, signing key, IdP sync | storage, GitHub, database, signing key for access tokens |

**What remains different:** per-project access, which is deferred. Everything else in the table is intended to match.

---

## 4. Design

### 4.1 Components

```
 Person (browser) ──► Web app (Angular, our fork) ──► ClearML API server (our fork) ◄── SDK (our fork)
                                                         │   ▲                       Agent (our fork)
                                                         │   └── checks IdP token signatures
                                                         ▼
                                              Keycloak (IdP, sign-in, tokens, device flow)
                                                         │
                                              RustFS (storage, temporary credentials)
                                              GitHub (App installation tokens)
                                              PostgreSQL / MongoDB (ClearML's own data)
```

No component besides the ClearML fork and the existing infrastructure is added.

### 4.2 Sign-in for people (web app)

1. The app redirects the person to Keycloak. They sign in there, with the MFA Keycloak requires.
2. Keycloak redirects back with a code. The ClearML server exchanges it for an IdP token and checks it, using PKCE to protect the exchange.
3. The ClearML server creates a session for the person and sets a session cookie, with a CSRF check on changes, as our server does today. No ClearML password is created.

### 4.3 Laptop enrolment (SDK): the same as ours

1. `clearml-init` (changed) starts the device flow: it prints a short code and address, and opens the browser.
2. The person signs in at Keycloak and confirms the code. The SDK receives an IdP token.
3. The SDK creates a key pair on the laptop. The private key is stored in the operating system's keychain where possible and never leaves the machine.
4. The SDK sends the public key, with the IdP token, to a new ClearML server endpoint. The server checks the IdP token, then stores the public key against the person's identity.
5. From then on, the SDK signs an assertion with its private key for each token request. The ClearML server checks the assertion against the stored public key and issues a short-lived access token. Each access token is then used for the requests.

Keycloak is used only for the sign-in during enrolment. It never needs to know about the device key, which is why this works without a Keycloak client per laptop.

### 4.4 Agent enrolment: admin only

1. `clearml-agent init` starts the device flow and shows a code. The agent's operator signs in with the IdP.
2. An admin approves the agent in the browser. The ClearML server refuses the approval unless the approving user holds the admin role.
3. The agent creates its own key pair, sends the public key to the server, and from then on proves itself with assertions as the laptop does.

The admin check is enforced by the ClearML server, not only by the IdP.

### 4.5 Revocation at two levels

- **Per device:** delete or disable that device's public key on the ClearML server. The next request from the device is refused, the same way our server does today.
- **Per user:** disable the user in the IdP. The ClearML server refreshes its copy of each user's status from the IdP every 60 seconds, as our server does today, and then refuses that user's devices and tokens. The delay is about a minute.

### 4.6 Per-job tokens

1. When a job starts, the ClearML server issues it a token. The token names the job, the run and the project, and expires when the job ends or after a short time.
2. The ClearML server signs the token with its own signing key, as our server does today. Keycloak is not involved.
3. The job uses that token for everything it does on the ClearML server, and the server checks the signature on each request.

This removes the dependency on Keycloak's token exchange. The signing key is a secret of the ClearML server and is covered in section 4.9.

### 4.7 Storage: short-lived credentials

1. The SDK or agent asks the ClearML server for storage access for a project, presenting its token.
2. The ClearML server checks the token and the project's permission, then asks RustFS for temporary credentials limited to that project's prefix, with a time limit. This is the same mechanism our server uses today (`services/storage.py`).
3. The credentials are returned to the caller and expire on their own.

The long-lived RustFS key is stored only on the ClearML server, as a file in a read-only mount.

### 4.8 GitHub

1. When a job needs a repository, the ClearML server mints a GitHub App installation token for that repository only. The token lasts one hour.
2. The agent uses it to clone the repository, then discards it.

The GitHub App's private key is stored only on the ClearML server, as a file in a read-only mount, as it is in our server today.

### 4.9 Secrets on the server

The server keeps these secrets, all as files in one read-only mount, with the exception of the database password, which may be an environment variable as it is today:

| Secret | Why the server needs it | Where |
|---|---|---|
| RustFS access key | issue temporary storage credentials | file |
| GitHub App private key | mint installation tokens | file |
| Database password | connect to the database | environment, as today |
| Signing key for access tokens | sign the access tokens of devices, agents and jobs | file |

The signing key is the one key that ClearML itself uses to sign: it signs the access tokens of devices, agents and jobs, as our server does. Keycloak signs the sign-in tokens, which the ClearML server only checks against Keycloak's public keys. The IdP sync secret of our current server is replaced by the ClearML server's own IdP client, which only verifies sign-in tokens.

The database and storage secrets can be rotated by replacing the file and restarting the server.

### 4.10 Audit

The fork adds an audit log in the ClearML server. It records who did what, when, and with which token, for sign-ins, enrolments, approvals, job tokens, storage requests and GitHub tokens. Keycloak's own sign-in events supplement it.

---

## 5. Changes by component

| Component | Language | Change | Size |
|---|---|---|---|
| API server: authentication | Python | replace the bearer and credential checks with IdP token checks | large |
| API server: device enrolment | Python | new endpoint: check the IdP token, store the device's public key | medium |
| API server: assertions and tokens | Python | check assertions against registered keys; issue short-lived access tokens (port of our `routers/auth.py` and `security/tokens.py`) | medium |
| API server: login and credentials | Python | remove the password, login, logout and access-key endpoints | medium |
| API server: users | Python / MongoDB | user record from the IdP identity, no password or key fields | medium |
| API server: revocation | Python | rely on IdP revocation and short access tokens; remove the revoked-token list | small |
| API server: per-job tokens | Python | issue job tokens with the server's signing key | medium |
| API server: storage | Python | temporary credentials from RustFS per project | medium |
| API server: GitHub | Python | installation tokens per job, using the App key; check the commit and the App installation at job submission | medium |
| API server: audit | Python | new audit log | medium |
| API server: agent approval | Python | check the approving admin on agent tokens | small |
| Web app | TypeScript (Angular) | remove the login and key pages; add IdP sign-in; use the server's session cookie; remove user management | large |
| SDK (`clearml`) | Python | remove key configuration; add device flow; create device key; sign assertions | medium |
| Agent (`clearml-agent`) | Python | remove key configuration; device flow; device key and assertions; use job tokens; GitHub token use | medium |
| File server | Python | check IdP tokens, or stop using it in favour of temporary storage credentials | medium |
| Configuration | — | secrets as files in one read-only mount; no secrets in the web app or the SDK | small |

Licences: the server is SSPL, which internal use is fine under. The SDK, agent and web app are Apache 2.0.

---

## 5a. Gaps between current mlops and the proposed ClearML integration

Each row compares what our solution does today with what the proposal does. "Closed by design" means the proposal reproduces the current behaviour; "open" means a gap remains that needs work or a decision.

| # | Area | Current mlops | Proposed ClearML | Status | Action |
|---|---|---|---|---|---|
| 1 | Sign-in for people | IdP sign-in, session cookie | IdP sign-in, then the ClearML server's session cookie | Closed by decision | Port `web_auth.py` and the CSRF check |
| 2 | Laptop enrolment | IdP sign-in, then a registered public key | Same | Closed by design | Port `routers/enroll.py` and the assertion check |
| 3 | Agent enrolment | Admin creates a one-time token | Admin approves the agent's device flow; server checks the admin role | Closed by design | Enforce the admin check on the server, not only in the IdP |
| 4 | Revocation, device | Key checked on every request | Key checked on every request | Closed by design | Same check, ported |
| 5 | Revocation, user | Disabled flag checked on every request; the flag is refreshed from the IdP every 60 seconds (`IDP_SYNC_INTERVAL`) | Same: status refreshed from the IdP every 60 seconds, then checked on every request | Closed by design: the same mechanism and delay | Port the sync loop (`services/directory.py`) |
| 6 | Job tokens | Run token; refused as soon as the job stops or is reassigned | Job token; checked on every request | Closed by decision | Refuse the token unless the job is still assigned or running, its run matches and its owner is enabled, as ours does |
| 7 | Access tokens | Signed by our server | Signed by the ClearML server | Closed by design | Port `security/tokens.py` |
| 8 | Storage access | Short-lived per-project credentials, checked against project membership | Same mechanism, checked against ClearML's company-wide access | Open: deferred with per-project access | Revisit with row 13 |
| 9 | GitHub | Read-only App. At job submission, refuses the job if the commit is not on GitHub or the App is not installed on the repository. Shows a repository's head commit in the UI | Installation tokens per job. ClearML's agent clones at the commit the SDK captured | Closed by decision: the submission check is ported; the head-commit lookup is optional | Port the commit and App checks into ClearML's job submission, so the job fails at once with a clear message |
| 10 | Audit | Audit events for sign-ins, tokens, storage and GitHub | None in ClearML's open-source server | Closed by design, once built | Build the audit log in the fork, covering the same events |
| 11 | Secrets | Storage, GitHub, database, signing key, IdP sync | Storage, GitHub, database, signing key | Closed by design; IdP sync replaced by a verify-only client | Load from files in one read-only mount |
| 12 | Client tool | `mlops` command with our SDK calls | `clearml` SDK | Accepted by decision: users move to `clearml` | Migration guide for existing scripts |
| 13 | Per-project access | Members per project; non-members get a 404 | Company-wide, or a public flag | Open: deferred by decision | 6 to 10 weeks later (section 7) |
| 14 | Datasets | Git commit and DVC hash linked to each run | ClearML's own dataset model | Open: the link to Git and DVC is lost | Accepted by decision |
| 15 | Dispatch and queues | Our agents, dispatch from the UI or CLI | ClearML queues and agents | Open: a different model | Accepted by decision |
| 16 | Web interface | Our own UI | ClearML's Angular UI, forked | Open: different look and features | Accepted by decision |
| 17 | Upkeep | One codebase, ours | Four forked repositories, merged by hand | Open: ongoing cost | Accepted by decision; one owner |

**Summary of the gaps that still need work before the first version:** none that are blocking. Row 9 is decided and needs porting. Row 8 (storage) is deferred to the topic of per-project access. Rows 1, 6 and 12 are decided. Rows 13 to 17 are accepted trade-offs. Row 5 is the same as ours.

---

## 6. Effort, risks and order of work

**Order**
1. **Spike (1 to 2 weeks):** the device enrolment and assertion flow; web-app sign-in; the admin-only agent approval; the job-token flow. Confirms the estimates.
2. **Server authentication:** IdP token checks and the identity object, with ClearML's existing tests.
3. **Storage and GitHub:** temporary storage credentials and installation tokens on the server.
4. **Clients:** SDK, then agent (device flow, job tokens, GitHub tokens), then web app.
5. **Audit and file server.**
6. **Security review** of the whole path before real use.
7. **Cut-over:** all clients at once.

**Risks**
- **Upstream merges.** Every ClearML release must be merged by hand, and the security changes touch central code.
- **Access tokens are signed by ClearML.** That key is a secret on the ClearML server. A leak would let someone forge access tokens until the key is replaced, so the key file needs the same protection as the storage key.
- **Cut-over.** Everyone switches at once, so the change has to be tested with every client before the switch.
- **Hidden dependencies.** Some ClearML services may rely on its user or company records in ways not yet checked.
- **Secrets on the server.** The storage key and GitHub key sit on the ClearML server. Protect the server host and limit who can read the mount.

**Not verified yet:** whether the agent accepts a short-lived token as its Git password, ClearML's web-app handling of its empty SSO placeholders, and whether the admin check on agent approval is done correctly in the port.

---

## 7. Later

- **Per-project access:** public or private projects, members, and roles per person, like Git. Not in ClearML's open-source code; estimated at 6 to 10 weeks on top of this design.

---

## 8. Confidence

- **Verified in code:** ClearML's authentication, credential and worker endpoints; the `Identity` object and how widely it is used; the file server's checks; our server's enrolment, storage, GitHub and secret handling.
- **Not verified:** the items listed in section 6.
- The effort figures are estimates for one experienced developer, not commitments.
