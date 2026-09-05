# BakiClear Integration Contract

## AI → Backend

StrategyProposal
NegotiationTurnDecision
MessageDraft

## Backend → AI

CustomerProfile
InvoiceContext
PaymentHistory
RiskContext
PolicyContext
NegotiationState

## Payment

POST /api/negotiations/{invoice_id}/create-order
POST /api/negotiations/{invoice_id}/verify-payment
GET /api/negotiations/{invoice_id}/status

## Human

GET /api/human-tasks
GET /api/human-tasks/{task_id}
POST /api/human-tasks/{task_id}/notes
POST /api/human-tasks/{task_id}/resolve

## Messaging

GET /api/messages