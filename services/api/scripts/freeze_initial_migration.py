"""Release utility: print a frozen empty-database revision for manual review.

This never runs against or writes a deployed database. Pass --write-initial only
while preparing the first, unreleased migration; future changes need new revisions.
"""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.main import app
from app.db import Base
from sqlalchemy import create_engine
from alembic.migration import MigrationContext
from alembic.autogenerate import produce_migrations, render_python_code

parser = argparse.ArgumentParser()
parser.add_argument("--write-initial", action="store_true")
args = parser.parse_args()
with create_engine("sqlite://").connect() as connection:
    script = produce_migrations(MigrationContext.configure(connection), Base.metadata)
header = '''"""Frozen initial Vector schema including identity and judge metadata."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
'''
content = header + render_python_code(script.upgrade_ops) + "\n\n\ndef downgrade():\n" + render_python_code(script.downgrade_ops) + "\n"
if args.write_initial:
    target = Path(__file__).resolve().parents[1] / "migrations/versions/0001_initial.py"
    target.write_text(content, encoding="utf-8")
    print(f"Frozen initial migration: {len(Base.metadata.tables)} tables; {len(content.splitlines())} lines")
else:
    print(content)
