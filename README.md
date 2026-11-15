# Rugas Queue Management

A queue management app for the Rugas Technologies Full Stack assignment.
Think of a bank or hospital token counter: a manager runs queues, people take
tokens, and the counter calls them one by one.

## What it does

1. **Manager login** — one manager account, token-based session.
2. **Create queues** — each queue has a name and its own token series
   (Billing issues `B-001, B-002…`, Support issues `S-001, S-002…`).
3. **Add people** — a token is created automatically for each person.
4. **Waiting list** — every queue shows its waiting tokens in order, with a
   live wait-time counter.
5. **Move tokens up / down** — reorder the line with one click.
6. **Call the top token** — "Call Next" (or the CALL button on the top
   ticket) moves the token at the front to NOW SERVING. Only one token can
   be served at a time per queue.
7. **Cancel a token** — removes it from the line.
8. **Dashboard** — waiting / serving / served counts, average wait time,
   longest-waiting person, per-queue load bars and tokens-per-hour trend.

## Design

Ticket-counter look: warm paper background, black ink, one signal-red
accent, chunky borders and hard shadows. No gradients, no glass — built to
look printed, like a real counter ticket.

## Run it

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open http://127.0.0.1:8000

**Demo manager login:** username `manager`, password `rugas123`
(change the seed password in `main.py` `init_db` for real use).

## Tech

- **Backend:** FastAPI + SQLite (plain `sqlite3`, no ORM)
- **Frontend:** single page, vanilla HTML/CSS/JS, no framework
- **Data:** `queue.db` (created automatically on first run)

## API

| Method | Route | What it does |
|---|---|---|
| POST | `/api/login` | Manager login, returns a session token |
| POST | `/api/logout` | End session |
| GET / POST | `/api/queues` | List / create queues |
| DELETE | `/api/queues/{id}` | Delete a queue |
| POST | `/api/queues/{id}/tokens` | Add a person, token auto-created |
| POST | `/api/tokens/{id}/move` | Move a token up or down |
| POST | `/api/queues/{id}/call-next` | Call the top token for service |
| POST | `/api/tokens/{id}/complete` | Mark the serving token done |
| POST | `/api/tokens/{id}/cancel` | Cancel a token |
| GET | `/api/dashboard` | Analytics: counts, avg wait, trends |
