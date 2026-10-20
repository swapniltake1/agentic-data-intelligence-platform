# Ola Safety and Customer Support — Retrieval Guide

## Purpose

This page helps the RAG assistant route customer-facing safety, account, fare-dispute, payment, and ride-support questions to official channels instead of improvising an operational policy.

Official support entry point: https://help.olacabs.com/support

The support portal currently groups help topics that include account issues, fares/charges/transactions, Ola Money, safety, and Ola services. Topics and links may change, so use the official portal as the authoritative starting point for current guidance.

## Answering support questions

### I have a fare, charge, or transaction dispute. What should I do?

Direct the user to the official Ola support flow for fares, charges, and transaction issues. Do not promise a refund, claim a charge is correct, or provide a specific resolution timeline unless an authoritative current source states it.

### I need help with a booking or account issue. What should I do?

Direct the user to the official support portal and the relevant booking/account category. This RAG knowledge base cannot access an individual's live booking, account, or case status.

### I have an immediate safety concern during a ride. What should I do?

Treat it as urgent. Encourage the person to use the relevant emergency services in their location if they are in immediate danger and the official in-app safety/support options where safe and available. Do not invent the current in-app button names, phone numbers, or escalation guarantees. Avoid delaying emergency assistance while searching documents.

### Can the assistant look up my ride or driver?

Not from the static knowledge base. That would require an authorized, secure integration and appropriate permissions. Never ask a user to post private booking details, driver phone numbers, OTPs, or precise trip coordinates into public logs or a shared knowledge base.

## RAG response rules

- Clearly distinguish general information from current official policy.
- Cite or name the official source document where available.
- If the answer isn't supported by indexed content, say that the knowledge base doesn't confirm it and direct the user to official support.
- Don't give legal guarantees or promise outcomes.
- Don't return personal information from trip rows.
- Never expose authentication tokens or one-time passwords.

## Review note

The support portal should be rechecked periodically. If this project is only an analytics demo and not a customer support tool, consider labelling responses as informational and not connected to live Ola account services.
