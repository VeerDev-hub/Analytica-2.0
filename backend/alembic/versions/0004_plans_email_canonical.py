"""plans and canonical email

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _canonical(email: str) -> str:
    local, _, dom = email.strip().lower().rpartition("@")
    local = local.split("+", 1)[0]
    if dom in ("gmail.com", "googlemail.com"):
        local = local.replace(".", "")
        dom = "gmail.com"
    return f"{local}@{dom}"


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("plan", sa.String(length=16), server_default="free", nullable=False),
    )
    op.add_column("users", sa.Column("email_canonical", sa.String(length=320), nullable=True))

    conn = op.get_bind()
    rows = conn.execute(sa.text("SELECT id, email FROM users")).all()
    seen: set[str] = set()
    for uid, email in rows:
        canon = _canonical(email)
        # Two existing accounts for one mailbox: keep the older one canonical, leave the
        # newer unindexed (NULL) so the unique index can be created.
        if canon in seen:
            continue
        seen.add(canon)
        conn.execute(
            sa.text("UPDATE users SET email_canonical = :c WHERE id = :id"),
            {"c": canon, "id": uid},
        )
    op.create_index(
        "ix_users_email_canonical", "users", ["email_canonical"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_users_email_canonical", table_name="users")
    op.drop_column("users", "email_canonical")
    op.drop_column("users", "plan")
