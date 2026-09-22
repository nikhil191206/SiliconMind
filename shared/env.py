"""Loads .env into process environment once, on first import. `.env` is
gitignored (never committed) and holds real credentials — WANDB_API_KEY,
GROQ_API_KEY, etc. — for local/dev runs. Safe to import repeatedly; `dotenv`
does not override variables already set in the real environment."""

from dotenv import load_dotenv

load_dotenv()
