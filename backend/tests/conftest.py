import os
import tempfile

# Point the app at a throwaway database and disable the LLM before anything imports app.config.
_db_dir = tempfile.mkdtemp()
# Set TEST_DATABASE_URL (e.g. a throwaway Postgres) to run the suite against another database.
os.environ["DATABASE_URL"] = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{_db_dir}/test.db"
os.environ["LLM_PROVIDER"] = "none"
