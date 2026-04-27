import os
os.environ.setdefault("JWT_SECRET", "x" * 32)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
