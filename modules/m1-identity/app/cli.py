"""m1-identity CLI.

Run inside the docker container:
  docker compose run --rm m1-identity python -m app.cli create-admin \\
    --email admin@example.com --password 'secret-32+chars' [--name 'Admin']

Or via Make:
  make create-admin EMAIL=admin@example.com PASSWORD='secret-32+chars'
"""
import argparse
import asyncio
import sys

from .admin_bootstrap import (
    AdminBootstrapError,
    create_admin_user,
)


async def _cmd_create_admin(args: argparse.Namespace) -> int:
    from . import db as db_module

    async with db_module.AsyncSessionLocal() as session:
        try:
            user = await create_admin_user(
                session,
                email=args.email,
                password=args.password,
                name=args.name,
                overwrite=args.overwrite,
            )
        except AdminBootstrapError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
    print(f"ok: id={user.id} email={user.email} role_id={user.role_id}")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="m1.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    create = sub.add_parser("create-admin", help="Create or rotate an admin user")
    create.add_argument("--email", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--name", default=None)
    create.add_argument(
        "--overwrite",
        action="store_true",
        help="Rotate password if the user already exists",
    )
    create.set_defaults(func=_cmd_create_admin)

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    return asyncio.run(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
