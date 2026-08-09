# Security Policy

## Reporting a vulnerability

Please use GitHub private vulnerability reporting for this repository when available. Do not disclose credentials, access tokens, customer materials, private project paths, or exploitable details in a public Issue.

Include the affected version, expected impact, reproduction steps using synthetic data, and any suggested mitigation.

## Scope

Security-sensitive areas include:

- worker dispatch and project-affinity checks;
- authorization and approval-state handling;
- external write permits and operation receipts;
- target/resource binding in operation adapters;
- callback identity and finalization gates;
- accidental publication of local or customer data.

The project does not treat a worker's success message alone as proof that an external write or verification succeeded.
