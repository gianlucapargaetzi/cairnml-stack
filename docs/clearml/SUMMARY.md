# ClearML with our identity provider: summary

The full report is in [idp-integration-report.md](idp-integration-report.md).

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
